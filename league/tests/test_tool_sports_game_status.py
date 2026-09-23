"""Known-value and fail-closed tests for the scoreboard status helper."""

import json
import unittest

from league.tools.sports_game_status import game_status


class GameStatusTests(unittest.TestCase):
    def snapshot(self, status='pre', now='2026-09-20T15:30:00Z',
                 start='2026-09-20T17:00:00Z',
                 received='2026-09-20T15:00:00Z'):
        return {
            'now': now,
            'feeds': {'sports': {'mlb': {
                'league': 'mlb',
                't': received,
                'events': [{
                    'id': '401872933',
                    'name': 'Away at Home',
                    'start': start,
                    'status': status,
                    'completed': status == 'post',
                }],
            }}},
        }

    def test_known_pregame_value(self):
        self.assertEqual(game_status(self.snapshot(), 'mlb', '401872933'), {
            'event_id': '401872933',
            'received_at': '2026-09-20T15:00:00Z',
            'start_time': '2026-09-20T17:00:00Z',
            'hours_to_start': 1.5,
            'status': 'pre',
            'completed': False,
            'pregame': True,
            'in_progress': False,
        })

    def test_offset_equivalence(self):
        ctx = self.snapshot(now='2026-09-20T11:30:00-04:00',
                            start='2026-09-20T13:00:00-04:00')
        state = game_status(ctx, 'mlb', '401872933')
        self.assertEqual(state['hours_to_start'], 1.5)
        self.assertTrue(state['pregame'])

    def test_live_and_completed(self):
        for status, live, complete in [('in', True, False),
                                       ('post', False, True)]:
            with self.subTest(status=status):
                ctx = self.snapshot(status=status,
                                    now='2026-09-20T18:00:00Z')
                state = game_status(ctx, 'mlb', '401872933')
                self.assertEqual(state['hours_to_start'], -1.0)
                self.assertIs(state['in_progress'], live)
                self.assertIs(state['completed'], complete)
                self.assertFalse(state['pregame'])

    def test_start_boundary_and_delayed_game_are_unknown(self):
        for now, hours in [('2026-09-20T17:00:00Z', 0.0),
                           ('2026-09-20T18:00:00Z', -1.0)]:
            with self.subTest(now=now):
                state = game_status(self.snapshot(now=now),
                                    'mlb', '401872933')
                self.assertEqual(state['status'], 'pre')
                self.assertEqual(state['hours_to_start'], hours)
                self.assertFalse(state['pregame'])
                self.assertIsNone(state['in_progress'])

    def test_reported_live_overrides_future_schedule(self):
        state = game_status(self.snapshot(status='in'), 'mlb', '401872933')
        self.assertTrue(state['in_progress'])
        self.assertFalse(state['pregame'])

    def test_unchanged_old_receipt_is_not_automatically_stale(self):
        ctx = self.snapshot(received='2026-09-19T15:00:00Z')
        self.assertTrue(game_status(ctx, 'mlb', '401872933')['pregame'])

    def test_exact_identity_and_ambiguity(self):
        ctx = self.snapshot()
        self.assertIsNone(game_status(ctx, 'mlb', 'Away at Home'))
        self.assertIsNone(game_status(ctx, 'mlb', '401872'))
        self.assertIsNone(game_status(ctx, 'nfl', '401872933'))
        events = ctx['feeds']['sports']['mlb']['events']
        events.append(dict(events[0]))
        self.assertIsNone(game_status(ctx, 'mlb', '401872933'))

    def test_missing_inputs(self):
        cases = [None, {}, {'now': '2026-09-20T15:30:00Z'},
                 {'now': '2026-09-20T15:30:00Z', 'feeds': None}]
        for ctx in cases:
            self.assertIsNone(game_status(ctx, 'mlb', '401872933'))
        for field in ('sports',):
            ctx = self.snapshot()
            ctx['feeds'][field] = None
            self.assertIsNone(game_status(ctx, 'mlb', '401872933'))
        for field in ('events', 't', 'league'):
            ctx = self.snapshot()
            del ctx['feeds']['sports']['mlb'][field]
            self.assertIsNone(game_status(ctx, 'mlb', '401872933'))
        ctx = self.snapshot()
        ctx['feeds']['sports']['mlb']['events'] = []
        self.assertIsNone(game_status(ctx, 'mlb', '401872933'))

    def test_invalid_or_naive_timestamps(self):
        for bad in (None, 'not-a-time', '2026-09-20T15:00:00'):
            for field in ('now', 't', 'start'):
                with self.subTest(value=bad, field=field):
                    ctx = self.snapshot()
                    board = ctx['feeds']['sports']['mlb']
                    if field == 'now':
                        ctx['now'] = bad
                    elif field == 't':
                        board['t'] = bad
                    else:
                        board['events'][0]['start'] = bad
                    self.assertIsNone(game_status(ctx, 'mlb', '401872933'))

    def test_future_receipt_is_rejected(self):
        ctx = self.snapshot(received='2026-09-20T15:30:01Z')
        self.assertIsNone(game_status(ctx, 'mlb', '401872933'))

    def test_invalid_and_contradictory_states(self):
        for status, completed in [('unknown', False), ('pre', True),
                                  ('in', True), ('post', False),
                                  ('pre', None), ('pre', 0)]:
            with self.subTest(status=status, completed=completed):
                ctx = self.snapshot()
                event = ctx['feeds']['sports']['mlb']['events'][0]
                event['status'] = status
                event['completed'] = completed
                self.assertIsNone(game_status(ctx, 'mlb', '401872933'))

    def test_invalid_lookup_arguments(self):
        ctx = self.snapshot()
        for event_id in ('', None, 401872933):
            self.assertIsNone(game_status(ctx, 'mlb', event_id))
        for league in ('', None, 1):
            self.assertIsNone(game_status(ctx, league, '401872933'))

    def test_deterministic_and_non_mutating(self):
        ctx = self.snapshot()
        before = json.dumps(ctx, sort_keys=True)
        first = game_status(ctx, 'mlb', '401872933')
        self.assertEqual(first, game_status(ctx, 'mlb', '401872933'))
        first['status'] = 'changed-by-caller'
        self.assertEqual(json.dumps(ctx, sort_keys=True), before)
        self.assertEqual(game_status(ctx, 'mlb', '401872933')['status'], 'pre')


if __name__ == '__main__':
    unittest.main()
