"""SIP relay timing, completeness, pagination and credential boundary, using invented bars."""
import datetime as dt
import io
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from scripts.data.sip import GatewayBars, NY, SIPError, SOURCE, completed_rows, relay_day

DAY = dt.date(2024, 1, 3)
HOURS = (570, 960)


def bar(minute=570, day=DAY):
    stamp = dt.datetime.combine(day, dt.time(), NY) + dt.timedelta(minutes=minute)
    return {'t': stamp.astimezone(dt.timezone.utc).isoformat(), 'o': 100, 'h': 102, 'l': 99, 'c': 101, 'v': 1000}


class Timing(unittest.TestCase):
    def test_bar_is_available_only_after_its_minute_finishes(self):
        rows = completed_rows([bar(570), bar(959), bar(960), bar(569)], DAY, HOURS)
        self.assertEqual([row['minute'] for row in rows], [571, 960])
        self.assertEqual(rows[0]['price'], rows[0]['close'])
        self.assertEqual(rows[0]['volume'], 1000)

    def test_half_day_and_summer_timezone(self):
        day = dt.date(2024, 7, 3)
        rows = completed_rows([bar(570, day), bar(779, day), bar(780, day)], day, (570, 780))
        self.assertEqual([row['minute'] for row in rows], [571, 780])

    def test_bad_prices_timestamps_and_conflicting_duplicates_fail(self):
        for change in ({'c': float('nan')}, {'h': 98}, {'l': -1}, {'v': -1}, {'t': '2024-01-03T09:30:00'}):
            with self.subTest(change=change), self.assertRaises(SIPError):
                completed_rows([dict(bar(), **change)], DAY, HOURS)
        self.assertEqual(len(completed_rows([bar(), bar()], DAY, HOURS)), 1)
        with self.assertRaises(SIPError):
            completed_rows([bar(), dict(bar(), v=2000)], DAY, HOURS)


class Opener:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return io.StringIO(json.dumps(next(self.pages)))


class Client(unittest.TestCase):
    def test_read_only_gateway_pagination_uses_raw_sip_and_historical_symbol_date(self):
        opener = Opener([{'bars': {'SPY': [bar()]}, 'next_page_token': 'next'},
                         {'bars': {'SPY': [bar(571)]}, 'next_page_token': None}])
        client = GatewayBars('https://gateway.invalid', 'test-token', opener=opener)
        self.assertEqual(len(client.fetch(['SPY'], DAY, HOURS)['SPY']), 2)
        for request in opener.requests:
            self.assertEqual(request.get_method(), 'GET')
            parsed = urlsplit(request.full_url)
            self.assertEqual(parsed.path, '/v1/alpaca/v2/stocks/bars')
            query = parse_qs(parsed.query)
            self.assertEqual((query['adjustment'], query['feed'], query['asof']), (['raw'], ['sip'], [str(DAY)]))
            self.assertNotIn('test-token', request.full_url)
        self.assertEqual(parse_qs(urlsplit(opener.requests[1].full_url).query)['page_token'], ['next'])

    def test_repeated_cursor_and_unexpected_symbol_are_errors(self):
        cases = [[{'bars': {'OTHER': []}}],
                 [{'bars': {}, 'next_page_token': 'a'}, {'bars': {}, 'next_page_token': 'a'}]]
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(SIPError):
                GatewayBars('https://gateway.invalid', 'test', opener=Opener(pages)).fetch(['SPY'], DAY, HOURS)


class Data:
    def __init__(self, roots=('SPY', 'XSP')):
        self.records = [{'type': 'file', 'kind': 'nbbo', 'root': root, 'date': str(DAY)} for root in roots]
        self.uploads = []
        self.confirm = True

    def run(self, command, timeout):
        if command.startswith('backfill.py records'):
            return True, '\n'.join(json.dumps(row) for row in self.records)
        if command.startswith('backfill.py ingest-underlying'):
            if self.confirm:
                self.records += [{'type': 'file', 'kind': 'underlying', 'root': row['root'], 'source': SOURCE}
                                 for row in json.loads(self.uploads[-1][1])]
            return True, 'ok'
        raise AssertionError(command)

    def upload(self, path, payload, mode):
        self.uploads.append((path, payload, mode))


class Gateway:
    def __init__(self, rows):
        self.rows = rows
        self.symbols = []

    def fetch(self, symbols, day, hours):
        self.symbols.append(symbols)
        return self.rows


class Calendar:
    def hours(self, day):
        return HOURS


class Relay(unittest.TestCase):
    def relay(self, data, gateway, mapping=lambda root, day: root):
        return relay_day(DAY, data, gateway=gateway, calendar=Calendar(), source_root=mapping)

    def test_only_data_crosses_to_box_and_indices_keep_their_own_source(self):
        data, gateway = Data(), Gateway({'SPY': [bar()]})
        result = self.relay(data, gateway)
        self.assertEqual(result['roots'], ['SPY'])
        self.assertEqual(gateway.symbols, [['SPY']])
        path, payload, mode = data.uploads[0]
        self.assertEqual(path, '/data/work/sip-2024-01-03.json')
        self.assertEqual(mode, 0o600)
        packet = json.loads(payload)[0]
        self.assertEqual(set(packet), {'root', 'day', 'completed_minutes', 'rows'})
        self.assertTrue(packet['completed_minutes'])
        self.assertEqual(packet['rows'][0]['minute'], 571)
        self.assertTrue(self.relay(data, gateway)['already'])
        self.assertEqual(len(gateway.symbols), 1)

    def test_missing_root_bars_prevent_partial_success(self):
        data = Data(('SPY', 'QQQ'))
        with self.assertRaises(SIPError):
            self.relay(data, Gateway({'SPY': [bar()]}))
        self.assertEqual(data.uploads, [])

    def test_symbol_alias_is_queried_but_packet_remains_canonical(self):
        data, gateway = Data(('META',)), Gateway({'FB': [bar()]})
        self.relay(data, gateway, lambda root, day: 'FB')
        self.assertEqual(gateway.symbols, [['FB']])
        self.assertEqual(json.loads(data.uploads[0][1])[0]['root'], 'META')

    def test_successful_command_without_journal_confirmation_is_not_success(self):
        data = Data()
        data.confirm = False
        with self.assertRaises(SIPError):
            self.relay(data, Gateway({'SPY': [bar()]}))
