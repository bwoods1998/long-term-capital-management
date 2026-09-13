"""Offline mechanical checks for private, source-grounded company research.

Quote membership and arithmetic are not semantic entailment or editorial review.
This module has no provider, ledger, publication, or brokerage capability.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re


SYMBOLS = ('NVDA', 'TSM', 'AVGO', 'CEG', 'VRT', 'MSFT', 'AMZN', 'GOOGL', 'META')
CASE_FIELDS = {'symbol', 'headline', 'metrics', 'claims', 'cash_flow_bridge',
               'dependencies', 'watchpoints', 'limitations'}
DECIMAL = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?')
_CURRENCY = r'(?:(?:US|NT|HK|C|A|R)?\$|[€£¥])'
_PREFIX = rf'(?:(?:[+\-−][ \t]*{_CURRENCY}?|{_CURRENCY}[ \t]*[+\-−]?)[ \t]*)?'
_DIGITS = r'(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?(?:[ \t]*%)?'
NUMBER = re.compile(rf'(?<![\w.,(+$€£¥−-])(?:\([ \t]*{_PREFIX}{_DIGITS}[ \t]*\)|{_PREFIX}{_DIGITS})(?!\w|[.,]\d)')
CASE_SCHEMA_HINT = {
    'symbol': 'TICKER', 'headline': 'Short research finding',
    'metrics': [{'id': 'ocf', 'label': 'Operating cash flow', 'value': '100',
                 'unit': 'USD millions', 'period': 'FY2026', 'evidence_id': 'supplied-passage-id',
                 'quote': 'Exact contiguous quote containing the directly reported number'}],
    'claims': [{'id': 'claim-1', 'text': 'Bounded sourced statement',
                'evidence_ids': ['supplied-passage-id'],
                'quotes': [{'evidence_id': 'supplied-passage-id', 'text': 'Exact contiguous source quote'}],
                'kind': 'reported|inference'}],
    'cash_flow_bridge': {'status': 'available|missing|not_comparable',
                        'operating_cash_flow_metric_id': None, 'cash_investment_metric_id': None,
                        'remainder': None, 'caveat': 'Scope and definition limits'},
    'dependencies': [{'symbol': 'ANOTHER_TICKER|EXTERNAL', 'mechanism': 'Sourced connection', 'evidence_ids': ['supplied-passage-id']}],
    'watchpoints': [{'question': 'Evidence that would change this case', 'evidence_ids': []}],
    'limitations': ['Missing evidence or scope limits'],
}
CRITIC_SCHEMA_HINT = {'symbol': 'TICKER', 'issues': [
    {'claim_id': 'existing-claim-id (or use metric_id instead)', 'text': 'Specific concern', 'evidence_ids': []}],
    'missing_evidence': ['Missing evidence'], 'verdict': 'revise|pass'}
COMPARISON_SCHEMA_HINT = {'symbol': 'TICKER', 'preferred': 'A|B|tie',
    'reasons': [{'text': 'Specific source-grounded comparison', 'evidence_ids': []}],
    'limitations': ['Limits of the comparison']}


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate JSON field')
        value[key] = item
    return value


def parse_object(response):
    """Parse one plain JSON object or one complete optional JSON fence."""
    if isinstance(response, dict):
        if 'output' not in response:
            return deepcopy(response)
        try:
            response = ''.join(part.get('text', '') for item in response.get('output', [])
                               if isinstance(item, dict) for part in item.get('content', [])
                               if isinstance(part, dict) and part.get('type') == 'output_text')
        except (TypeError, AttributeError):
            raise ValueError('Malformed response text') from None
    if not isinstance(response, str) or len(response) > 150000:
        raise ValueError('Expected bounded JSON text')
    value = response.strip()
    wrapper = re.fullmatch(r'```(?:json)?\r?\n([\s\S]*?)\r?\n```', value)
    if wrapper:
        value = wrapper.group(1)

    def nonfinite(_):
        raise ValueError('Non-finite JSON value')

    value = json.loads(value, object_pairs_hook=_unique, parse_constant=nonfinite)
    if not isinstance(value, dict):
        raise ValueError('Expected one JSON object')
    return value


def _keys(value, expected):
    return isinstance(value, dict) and set(value) == set(expected)


def _text(value, maximum=1600):
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum


def _list(value, minimum=0, maximum=30):
    return isinstance(value, list) and minimum <= len(value) <= maximum


def _day(value):
    if not isinstance(value, str):
        raise ValueError('Invalid date')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Invalid date')
    return parsed


def _number(value):
    if not isinstance(value, str) or not DECIMAL.fullmatch(value) or len(value) > 40:
        raise ValueError('Expected a bounded plain decimal string')
    parsed = Decimal(value)
    if abs(parsed) > Decimal('1e15'):
        raise ValueError('Numeric value exceeds protocol range')
    return parsed


def _quoted_number(value, quote, source_text):
    """Require a whole original numeric token inside an exact quote occurrence.

Tokenizing only the quote would let '25' strip the sign from source '(25)',
or '250' strip the leading digit from '1,250'. Units still require review.
"""
    if not _text(quote, 6000):
        return False
    for match in NUMBER.finditer(source_text):
        matched = match.group()
        negative = matched.startswith('(') and matched.endswith(')')
        cleaned = re.sub(_CURRENCY, '', matched).strip('()').replace(',', '').replace('%', '').replace('−', '-')
        cleaned = re.sub(r'[ \t]', '', cleaned)
        try:
            number = Decimal(cleaned)
            if negative:
                number = -abs(number)
            if number == value:
                # Search only quote occurrences that could contain this whole
                # token, avoiding quadratic scans for repeated short quotes.
                start = source_text.find(quote, max(0, match.end() - len(quote)),
                                         min(len(source_text), match.start() + len(quote)))
                if start != -1 and start <= match.start() and match.end() <= start + len(quote):
                    return True
        except InvalidOperation:
            continue
    return False


def _company(company):
    if not isinstance(company, dict) or company.get('symbol') not in SYMBOLS:
        raise ValueError('Unknown company')
    cutoff = _day(company['as_of'])
    if not _list(company.get('sources'), 1, 40):
        raise ValueError('Company requires frozen sources')
    sources = {}
    for source in company['sources']:
        if (not isinstance(source, dict) or not {'id', 'published_at', 'sha256', 'text'} <= set(source)
                or not _text(source['id'], 160) or not _text(source['text'], 2000000)
                or source['id'] in sources):
            raise ValueError('Invalid frozen source')
        if hashlib.sha256(source['text'].encode()).hexdigest() != source['sha256']:
            raise ValueError('Frozen source text hash mismatch')
        published = _day(source['published_at'])
        sources[source['id']] = {**source, 'eligible': published <= cutoff}
    return sources


class _Checks:
    def __init__(self, company):
        self.symbol = company.get('symbol') if isinstance(company, dict) else None
        self.sources = _company(company)
        self.errors = []
        self.checks = {name: True for name in ('schema', 'citation_membership', 'publication_cutoff',
                       'quote_membership', 'numeric_lexical', 'bridge_references', 'bridge_comparability',
                       'bridge_arithmetic')}
        self.counts = {'metrics': 0, 'metrics_checked': 0, 'claims': 0, 'quoted_claims': 0,
                       'citations_checked': 0, 'quotes_checked': 0, 'dependencies': 0,
                       'watchpoints': 0, 'bridge_available': 0}

    def fail(self, check, path):
        self.checks[check] = False
        self.errors.append({'check': check, 'path': path})

    def citations(self, ids, path, minimum=1):
        if not _list(ids, minimum, 20) or any(not isinstance(x, str) for x in ids) or len(ids) != len(set(ids)):
            self.fail('schema', path)
            return False
        valid = True
        for identifier in ids:
            source = self.sources.get(identifier)
            if source is None:
                self.fail('citation_membership', path); valid = False
            elif not source['eligible']:
                self.fail('publication_cutoff', path); valid = False
            else:
                self.counts['citations_checked'] += 1
        return valid

    def quote(self, identifier, text, path):
        source = self.sources.get(identifier) if isinstance(identifier, str) else None
        valid = self.citations([identifier], path)
        if not _text(text, 6000) or source is None or text not in source['text']:
            self.fail('quote_membership', path)
            return False
        if valid:
            self.counts['quotes_checked'] += 1
        return valid

    def result(self):
        return {'valid': all(self.checks.values()), 'checks': self.checks, 'errors': self.errors,
                'counts': self.counts, 'requires_editorial_review': True,
                'scope': 'mechanical_source_membership_and_arithmetic_only'}


def check_case(case, company):
    """Check a private draft against its exact supplied company source packet."""
    check = _Checks(company)
    if not _keys(case, CASE_FIELDS) or case.get('symbol') != check.symbol or not _text(case.get('headline'), 220):
        check.fail('schema', 'case')
        return check.result()
    metrics = {}
    if not _list(case['metrics'], 0, 30):
        check.fail('schema', 'metrics')
    else:
        check.counts['metrics'] = len(case['metrics'])
        for index, item in enumerate(case['metrics']):
            path = f'metrics[{index}]'
            if (not _keys(item, ('id', 'label', 'value', 'unit', 'period', 'evidence_id', 'quote'))
                    or any(not _text(item[key], 180) for key in ('id', 'label', 'unit', 'period'))
                    or item['id'] in metrics):
                check.fail('schema', path); continue
            metrics[item['id']] = item
            try:
                number = _number(item['value'])
            except ValueError:
                check.fail('schema', path + '.value'); continue
            quote_ok = check.quote(item['evidence_id'], item['quote'], path + '.quote')
            source = check.sources.get(item['evidence_id']) if isinstance(item['evidence_id'], str) else None
            if (not isinstance(item['quote'], str) or source is None
                    or not _quoted_number(number, item['quote'], source['text'])):
                check.fail('numeric_lexical', path + '.value')
            elif quote_ok:
                check.counts['metrics_checked'] += 1
    if not _list(case['claims'], 1, 16):
        check.fail('schema', 'claims')
    else:
        check.counts['claims'] = len(case['claims'])
        ids = set()
        for index, item in enumerate(case['claims']):
            path = f'claims[{index}]'
            if (not _keys(item, ('id', 'text', 'evidence_ids', 'quotes', 'kind'))
                    or not _text(item['id'], 180) or item['id'] in ids
                    or not _text(item['text']) or item['kind'] not in ('reported', 'inference')):
                check.fail('schema', path); continue
            ids.add(item['id'])
            cited = check.citations(item['evidence_ids'], path + '.evidence_ids')
            if not _list(item['quotes'], 1, 20):
                check.fail('schema', path + '.quotes'); continue
            quoted = set()
            for qindex, quote in enumerate(item['quotes']):
                qpath = path + f'.quotes[{qindex}]'
                if not _keys(quote, ('evidence_id', 'text')) or not isinstance(quote['evidence_id'], str):
                    check.fail('schema', qpath); cited = False; continue
                quoted.add(quote['evidence_id'])
                cited = check.quote(quote['evidence_id'], quote['text'], qpath) and cited
            if (not isinstance(item['evidence_ids'], list)
                    or any(not isinstance(x, str) for x in item['evidence_ids'])
                    or quoted != set(item['evidence_ids'])):
                check.fail('citation_membership', path + '.quotes'); cited = False
            if cited:
                check.counts['quoted_claims'] += 1
    _bridge(case['cash_flow_bridge'], metrics, check)
    for field, fields in (('dependencies', ('symbol', 'mechanism', 'evidence_ids')),
                          ('watchpoints', ('question', 'evidence_ids'))):
        if not _list(case[field], 0 if field == 'dependencies' else 1, 16):
            check.fail('schema', field); continue
        check.counts[field] = len(case[field])
        for index, item in enumerate(case[field]):
            path = f'{field}[{index}]'
            if not _keys(item, fields):
                check.fail('schema', path); continue
            if field == 'dependencies' and (item['symbol'] not in (*SYMBOLS, 'EXTERNAL') or item['symbol'] == check.symbol):
                check.fail('schema', path + '.symbol')
            if not _text(item['mechanism'] if field == 'dependencies' else item['question']):
                check.fail('schema', path)
            check.citations(item['evidence_ids'], path + '.evidence_ids', 0 if field == 'watchpoints' else 1)
    if not _list(case['limitations'], 1, 16) or any(not _text(x) for x in case['limitations']):
        check.fail('schema', 'limitations')
    return check.result()


def _bridge(bridge, metrics, check):
    fields = ('status', 'operating_cash_flow_metric_id', 'cash_investment_metric_id', 'remainder', 'caveat')
    if not _keys(bridge, fields) or bridge['status'] not in ('available', 'missing', 'not_comparable') or not _text(bridge['caveat']):
        check.fail('schema', 'cash_flow_bridge'); return
    refs = (bridge['operating_cash_flow_metric_id'], bridge['cash_investment_metric_id'])
    if any(ref is not None and (not isinstance(ref, str) or ref not in metrics) for ref in refs):
        check.fail('bridge_references', 'cash_flow_bridge'); return
    if bridge['status'] != 'available':
        if bridge['remainder'] is not None:
            check.fail('bridge_arithmetic', 'cash_flow_bridge.remainder')
        if bridge['status'] == 'missing' and all(ref is not None for ref in refs):
            check.fail('bridge_references', 'cash_flow_bridge.status')
        return
    check.counts['bridge_available'] = 1
    if None in refs or refs[0] == refs[1]:
        check.fail('bridge_references', 'cash_flow_bridge'); return
    ocf, investment = (metrics[ref] for ref in refs)
    if ocf['unit'] != investment['unit'] or ocf['period'] != investment['period']:
        check.fail('bridge_comparability', 'cash_flow_bridge')
    try:
        values = [_number(x) for x in (ocf['value'], investment['value'], bridge['remainder'])]
        with localcontext() as context:
            context.prec = 80
            # Preserve the reported signed cash-flow metric, then use its
            # outflow magnitude for cash remaining after equipment purchases.
            if values[0] - abs(values[1]) != values[2]:
                check.fail('bridge_arithmetic', 'cash_flow_bridge.remainder')
    except ValueError:
        check.fail('bridge_arithmetic', 'cash_flow_bridge.remainder')


def check_critic(critic, company, case=None):
    check = _Checks(company)
    if (not _keys(critic, ('symbol', 'issues', 'missing_evidence', 'verdict'))
            or critic['symbol'] != check.symbol or critic['verdict'] not in ('revise', 'pass')
            or not _list(critic['issues'], 0, 30) or not _list(critic['missing_evidence'], 0, 20)
            or any(not _text(x) for x in critic['missing_evidence'])):
        check.fail('schema', 'critic'); return check.result()
    for index, issue in enumerate(critic['issues']):
        path = f'issues[{index}]'
        if not isinstance(issue, dict) or set(issue) not in ({'claim_id', 'text', 'evidence_ids'}, {'metric_id', 'text', 'evidence_ids'}):
            check.fail('schema', path); continue
        key = 'claim_id' if 'claim_id' in issue else 'metric_id'
        if not _text(issue[key], 180) or not _text(issue['text']):
            check.fail('schema', path); continue
        if case is not None:
            refs = {x.get('id') for x in case.get('claims' if key == 'claim_id' else 'metrics', [])
                    if isinstance(x, dict) and isinstance(x.get('id'), str)}
            if issue[key] not in refs:
                check.fail('schema', path + '.' + key)
        check.citations(issue['evidence_ids'], path + '.evidence_ids', 0)
    if critic['verdict'] == 'pass' and (critic['issues'] or critic['missing_evidence']):
        check.fail('schema', 'critic.verdict')
    return check.result()


def check_comparison(result, company):
    check = _Checks(company)
    if (not _keys(result, ('symbol', 'preferred', 'reasons', 'limitations'))
            or result['symbol'] != check.symbol or result['preferred'] not in ('A', 'B', 'tie')
            or not _list(result['reasons'], 1, 12) or not _list(result['limitations'], 1, 12)
            or any(not _text(x) for x in result['limitations'])):
        check.fail('schema', 'comparison'); return check.result()
    for index, reason in enumerate(result['reasons']):
        if not _keys(reason, ('text', 'evidence_ids')) or not _text(reason['text']):
            check.fail('schema', f'reasons[{index}]'); continue
        check.citations(reason['evidence_ids'], f'reasons[{index}].evidence_ids', 0)
    return check.result()


def compare_checks(before, after):
    """Mechanical changes, not a claim of substantive research improvement."""
    return {'baseline_valid': before['valid'], 'revision_valid': after['valid'],
            'fixed_checks': sorted(k for k in before['checks'] if not before['checks'][k] and after['checks'][k]),
            'regressed_checks': sorted(k for k in before['checks'] if before['checks'][k] and not after['checks'][k]),
            'count_changes': {k: after['counts'][k] - before['counts'][k] for k in before['counts']},
            'requires_editorial_review': True}
