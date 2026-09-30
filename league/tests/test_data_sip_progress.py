"""Historical gaps cannot strand later dates or become image readiness. Invented metadata only."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

DATA = Path(__file__).resolve().parents[2] / 'scripts' / 'data'
sys.path.insert(0, str(DATA))
import boxlib as bl
import complete
import images
import sip
import storelib as sl
from sip_progress import Progress, MAX_ATTEMPTS

DAYS = ['2022-03-08', '2022-03-09']


def plan():
    return {'schema': sl.SIP_COVERAGE_SCHEMA, 'source': sl.SIP_SOURCE, 'start': DAYS[0], 'end': DAYS[1],
            'days': [{'day': d, 'window': 'train', 'hours': [570, 573], 'roots': {'PLTR': 'PLTR', 'SPY': 'SPY'}} for d in DAYS]}


def receipt(day, root, *, full=False):
    return {'day': day, 'root': root, 'source': sl.SIP_SOURCE, 'source_symbol': root,
            **sl.sip_coverage([571, 572, 573] if full else [571], (570, 573)),
            'status': 'complete' if full else 'partial', 'file_sha256': 'a' * 64 if full else None,
            'packet_sha256': 'b' * 64 if full else 'c' * 64,
            'verification': 'current_file_hash_and_grid' if full else None}


def finished(queue):
    for day in DAYS:
        queue.observe(day, [receipt(day, r, full=True) for r in ('PLTR', 'SPY')])
        queue.scanned(day)


def identities():
    return [{**receipt(day, root, full=True), 'actual_sha256': 'a' * 64} for day in DAYS for root in ('PLTR', 'SPY')]


class DurableGaps(unittest.TestCase):
    def test_later_dates_advance_and_budget_survives_crash_then_evidence_reconsideration(self):
        now = [1000.0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sip.sqlite'
            with Progress(path, plan(), clock=lambda: now[0]) as q:
                due = q.reserve(DAYS[0], [receipt(DAYS[0], 'PLTR'), receipt(DAYS[0], 'SPY', full=True)])
                self.assertEqual(due, ['PLTR'])
                # Crash after reservation, before any response: the attempt was already committed.
            with Progress.existing(path, clock=lambda: now[0]) as q:
                self.assertEqual(q.due_days(), [])
                q.scanned(DAYS[0])
                q.observe(DAYS[1], [receipt(DAYS[1], r, full=True) for r in ('PLTR', 'SPY')])
                q.scanned(DAYS[1])
                self.assertEqual(q.summary()['scanned_days'], 2)
                self.assertEqual(q.summary()['unresolved'], 1)
                for attempt in range(2, MAX_ATTEMPTS + 1):
                    now[0] += 300 * 2 ** (attempt - 2)
                    self.assertEqual(q.due_days(), [DAYS[0]])
                    self.assertEqual(q.reserve(DAYS[0], [receipt(DAYS[0], 'PLTR'), receipt(DAYS[0], 'SPY', full=True)]), ['PLTR'])
                    q.record(DAYS[0], [receipt(DAYS[0], 'PLTR')])
                now[0] += 10000
                self.assertEqual(q.due_days(), [])
                self.assertEqual(q.summary()['deferred'], 1)
                self.assertFalse(q.summary()['complete'])
                self.assertEqual(q.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], MAX_ATTEMPTS)
                evidence = 'Provider case example-17 confirms corrected March 8 PLTR packet is now available.'
                self.assertTrue(q.reconsider(DAYS[0], 'PLTR', evidence))
                self.assertFalse(q.reconsider(DAYS[0], 'PLTR', evidence))
                self.assertEqual(q.db.execute('SELECT attempts,budget FROM roots WHERE root=? AND day=?',
                                            ('PLTR', DAYS[0])).fetchone(), (3, 6))
                self.assertEqual(q.reserve(DAYS[0], [receipt(DAYS[0], 'PLTR'), receipt(DAYS[0], 'SPY', full=True)]), ['PLTR'])
                q.record(DAYS[0], [receipt(DAYS[0], 'PLTR', full=True)])
                self.assertTrue(q.summary()['complete'])
                self.assertEqual(q.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 4)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_lost_acknowledgement_can_resolve_only_from_current_byte_and_grid_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Progress(Path(tmp) / 'sip.sqlite', plan()) as q:
                q.reserve(DAYS[0], [receipt(DAYS[0], r) for r in ('PLTR', 'SPY')])
                bad = [receipt(DAYS[0], r, full=True) for r in ('PLTR', 'SPY')]
                bad[0]['verification'] = None
                with self.assertRaisesRegex(ValueError, 'verified bytes'):
                    q.observe(DAYS[0], bad)
                self.assertEqual(q.summary()['unresolved'], 2)
                finished(q)
                self.assertTrue(q.summary()['complete'])
                self.assertEqual(q.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 2)

    def test_changed_bytes_or_journal_identity_reopens_a_complete_gap(self):
        for edit in (lambda f: f.update(actual_sha256='different'),
                     lambda f: f.update(file_sha256='different'),
                     lambda f: f.update(source='changed'), lambda f: f.update(source_symbol='OLD'),
                     lambda f: f.update(packet_sha256='different')):
            with self.subTest(edit=edit), tempfile.TemporaryDirectory() as tmp:
                with Progress(Path(tmp) / 'sip.sqlite', plan()) as q:
                    finished(q)
                    before = q.summary()['receipt_sha256']
                    q.compare_files(identities())
                    self.assertEqual(q.summary()['receipt_sha256'], before)
                    files = identities()
                    edit(files[0])
                    q.compare_files(files)
                    self.assertFalse(q.summary()['complete'])
                    self.assertEqual(q.summary()['unresolved'], 1)
                    self.assertNotIn('receipt_sha256', q.summary())

    def test_plan_binds_source_schema_root_symbol_calendar_and_window(self):
        mutations = [lambda p: p.update(source='other source'), lambda p: p.update(schema=99),
                     lambda p: p['days'][0]['roots'].pop('PLTR'),
                     lambda p: p['days'][0]['roots'].update(PLTR='OLD'),
                     lambda p: p['days'][0].update(hours=[570, 572]),
                     lambda p: p['days'][0].update(window='holdout')]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sip.sqlite'
            with Progress(path, plan()) as q:
                finished(q)
            for mutate in mutations:
                modified = copy.deepcopy(plan())
                mutate(modified)
                with self.assertRaisesRegex(ValueError, 'plan changed'):
                    Progress(path, modified)
            with Progress.existing(path) as q:
                self.assertTrue(q.summary()['complete'])
                with self.assertRaisesRegex(ValueError, 'roots differ'):
                    q.observe(DAYS[0], [receipt(DAYS[0], 'SPY', full=True)])
                with self.assertRaisesRegex(ValueError, 'file plan changed'):
                    q.compare_files(identities()[1:])

    def test_observation_and_attempt_receipts_reject_wrong_day_source_and_forged_completeness(self):
        mutations = [lambda r: r.update(day=DAYS[1]), lambda r: r.update(source_symbol='OTHER'),
                     lambda r: r.update(schema=99), lambda r: r.update(source='unverified label'),
                     lambda r: r.update(expected=0, known=0), lambda r: r.update(file_sha256=None),
                     lambda r: r.update(verification=None), lambda r: r.update(complete='true'),
                     lambda r: r.update(missing_minutes=[571]), lambda r: r.update(known=True)]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp:
                with Progress(Path(tmp) / 'sip.sqlite', plan()) as q:
                    q.reserve(DAYS[0], [receipt(DAYS[0], r) for r in ('PLTR', 'SPY')])
                    bad = receipt(DAYS[0], 'PLTR', full=True)
                    mutate(bad)
                    with self.assertRaises(ValueError):
                        q.observe(DAYS[0], [bad, receipt(DAYS[0], 'SPY', full=True)])
                    with self.assertRaises(ValueError):
                        q.record(DAYS[0], [bad])
                    self.assertEqual(q.summary()['unresolved'], 2)


class Controller(unittest.TestCase):
    def test_completed_certificate_sleeps_but_changed_desired_version_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            state = Path(tmp)
            bl.write_json(state / 'completion-config.json', {'enabled': True, 'version': 'first'})
            # Obtain the locally recorded requested identity without constructing an operations client.
            bl.write_json(state / 'completion.json', {'schema': complete.SCHEMA, 'phase': 'complete'})
            with patch.object(complete, 'Operations', side_effect=AssertionError('completed certificates do not poll')):
                result = complete.Completion(state).tick()
                certificate = {'scope': 'immutable_staged_checkpoint_pair', 'checkpoints': {'gym': ['a'], 'gate': ['b']}}
                bl.write_json(state / 'completion.json', result)
                bl.write_json(state / 'images-ready.json', certificate)
                self.assertEqual(complete.Completion(state).tick()['phase'], 'complete')
                bl.write_json(state / 'completion-config.json', {'enabled': True, 'version': 'second'})
                changed = complete.Completion(state).tick()
                self.assertEqual(changed['phase'], 'review_required')
                self.assertFalse((state / 'images-ready.json').exists())
                archived = list(state.glob('images-ready-archived-*.json'))
                self.assertEqual(len(archived), 1)
                self.assertEqual(bl.read_json(archived[0]), certificate)
                self.assertEqual(complete.Completion(state).tick()['phase'], 'review_required')

    def test_scanning_all_days_with_gaps_never_builds_or_advertises_ready(self):
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            state = Path(tmp)
            bl.write_json(state / 'completion-config.json', {'enabled': True})
            bl.write_json(state / 'completion.json', {'schema': complete.SCHEMA, 'phase': 'sip', 'next_day': str(sl.HOLDOUT[1])})
            summary = {'complete': False, 'unresolved': 1, 'deferred': 1}
            ops = SimpleNamespace(relay_chunk=lambda *_: dict(summary), retry_gaps=lambda: dict(summary),
                                  build=lambda *_: self.fail('gap cannot build an image'))
            first = complete.Completion(state, operations=ops).tick()
            self.assertEqual(first['phase'], 'sip_gaps')
            self.assertGreater(first['next_day'], str(sl.HOLDOUT[1]))
            second = complete.Completion(state, operations=ops).tick()
            self.assertEqual(second['phase'], 'sip_gaps')
            self.assertFalse((state / 'images-ready.json').exists())

    def test_legacy_completion_restarts_scan_and_preserves_old_image_records(self):
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            state = Path(tmp)
            legacy = {'schema': 1, 'phase': 'complete', 'ready': {'gate_checkpoint': 'old'}}
            bl.write_json(state / 'completion-config.json', {'enabled': True})
            bl.write_json(state / 'completion.json', legacy)
            bl.write_json(state / 'images-ready.json', legacy['ready'])
            bl.write_json(state / 'images.json', {'gate': {'current_checkpoint': 'immutable-old'}})
            starts = []
            def relay(start, end):
                starts.append(start)
                return {'complete': False, 'unresolved': 1}
            result = complete.Completion(state, operations=SimpleNamespace(relay_chunk=relay)).tick()
            self.assertEqual(starts, [sl.TRAIN[0]])
            self.assertEqual(result['phase'], 'sip')
            self.assertEqual(bl.read_json(state / 'completion-legacy-sip-v1.json'), legacy)
            self.assertFalse((state / 'images-ready.json').exists())
            self.assertEqual(bl.read_json(state / 'images-ready-legacy-sip-v1.json'), legacy['ready'])
            self.assertEqual(bl.read_json(state / 'images.json')['gate']['current_checkpoint'], 'immutable-old')

    def test_prebuild_and_prepublication_changes_leave_readiness_false(self):
        for phase in ('gym', 'gate', 'calibrate'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
                state = Path(tmp)
                bl.write_json(state / 'completion-config.json', {'enabled': True})
                bl.write_json(state / 'completion.json', {'schema': complete.SCHEMA, 'phase': phase, 'sip_receipt': 'old'})
                ops = SimpleNamespace(sip_ready=lambda: {'complete': False, 'unresolved': 1},
                                      build=lambda *_: self.fail('changed data cannot build'),
                                      calibrate=lambda *_: self.fail('changed data cannot publish'))
                self.assertEqual(complete.Completion(state, operations=ops).tick()['phase'], 'sip_gaps')
                self.assertFalse((state / 'images-ready.json').exists())

    def test_relay_days_records_attempt_before_call_and_continues_after_partial_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops = object.__new__(complete.Operations)
            ops.data = object()
            calls = []
            with Progress(Path(tmp) / 'sip.sqlite', plan()) as q:
                def status(data, day):
                    return {'roots': [receipt(str(day), r) for r in ('PLTR', 'SPY')]}
                def relay(day, data, **kwargs):
                    self.assertTrue(kwargs['allow_gaps'])
                    self.assertEqual(q.db.execute('SELECT COUNT(*) FROM attempts WHERE day=?', (str(day),)).fetchone()[0], 2)
                    kwargs['check_lease']()
                    calls.append(str(day))
                    return {'coverage': [receipt(str(day), r, full=(r == 'SPY' or str(day) == DAYS[1])) for r in ('PLTR', 'SPY')]}
                with patch.object(sip, 'status_day', status), patch.object(sip, 'relay_day', relay), patch.object(sl, 'in_quiet', return_value=False):
                    ops._relay_days([dt.date.fromisoformat(d) for d in DAYS], q, object(), lambda: None)
                self.assertEqual(calls, DAYS)
                self.assertEqual(q.summary()['unresolved'], 1)
                self.assertEqual(q.summary()['scanned_days'], 2)

    def test_quiet_window_starts_no_sip_request_or_reservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops = object.__new__(complete.Operations)
            ops.data = object()
            with Progress(Path(tmp) / 'sip.sqlite', plan()) as q, patch.object(sl, 'in_quiet', return_value=True), \
                    patch.object(sip, 'status_day') as status:
                with self.assertRaisesRegex(RuntimeError, 'quiet window'):
                    ops._relay_days([dt.date.fromisoformat(DAYS[0])], q, object(), lambda: None)
                status.assert_not_called()
                self.assertEqual(q.db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_exhausted_or_backoff_retry_queue_does_not_wake_the_box(self):
        for exhausted in (False, True):
            with self.subTest(exhausted=exhausted), tempfile.TemporaryDirectory() as tmp:
                state = Path(tmp)
                with Progress(state / 'sip-progress.sqlite', plan(), clock=lambda: 10**15) as q:
                    q.reserve(DAYS[0], [receipt(DAYS[0], r) for r in ('PLTR', 'SPY')])
                    if exhausted:
                        with q.db:
                            q.db.execute('UPDATE roots SET attempts=budget')
                ops = object.__new__(complete.Operations)
                ops.state = state
                ops.data = SimpleNamespace(wake=lambda: self.fail('no-due queue must not wake the box'))
                self.assertEqual(ops.retry_gaps()['deferred'], 2 if exhausted else 0)

    def test_source_check_runs_under_same_box_lease_before_any_snapshot_and_recovers_backfill(self):
        held, running = [False], [True]
        class Lease:
            def __init__(self, api, box): self_box.assertEqual(box, 'sb_data')
            def __enter__(self): held[0] = True; return self
            def __exit__(self, *args): held[0] = False
            def check(self): self_box.assertTrue(held[0])
        class API:
            def download(self, box, path, **kwargs):
                if path.endswith('progress.json'):
                    return b'{"stages":{"1":{"planned":1}}}'
                return b'{"type":"task","stage":1,"task":"day:SPY:2022-03-08","status":"ok"}\n'
        data = SimpleNamespace(backfill_running=lambda: running[0], stop_backfill=lambda: running.__setitem__(0, False),
                               start_backfill=lambda _: running.__setitem__(0, True))
        def source_check(box):
            self.assertEqual(box, 'sb_data')
            self.assertTrue(held[0])
            self.assertFalse(running[0])
            raise RuntimeError('canonical file changed before snapshot')
        self_box = self
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            bl.write_json(bl.DATA_BOX, {'box_id': 'sb_data', 'runs': [{'args': '--stages 1'}]})
            with patch.object(bl, 'RemoteLease', Lease), patch.object(bl, 'ensure_running'), \
                    patch('nightly.BoxHandle', return_value=data), patch.object(images, 'checkpoint_with_retry') as checkpoint:
                with self.assertRaisesRegex(RuntimeError, 'changed before snapshot'):
                    images.build('gym', version='test', force=False, api=API(), needs=(1,), source_check=source_check)
                checkpoint.assert_not_called()
                self.assertTrue(running[0])
                self.assertFalse(held[0])

    def test_snapshot_evidence_explicitly_excludes_retained_forward_files(self):
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
            state = Path(tmp)
            bl.write_json(bl.DATA_BOX, {'box_id': 'sb_data'})
            bl.write_json(bl.UNIVERSE, {'roots': ['SPY', 'PLTR']})
            with Progress(state / 'sip-progress.sqlite', plan()) as q:
                finished(q)
                sha = q.summary()['receipt_sha256']
            ops = object.__new__(complete.Operations)
            ops.state, ops.data, ops.api = state, SimpleNamespace(box_id='sb_data'), object()
            ops.sip_plan = lambda **_: {'plan': plan(), 'files': identities()}
            def build(kind, **kwargs):
                proof = kwargs['source_check']('sb_data')
                self.assertEqual(proof['scope'], 'historical_stock_underlying_completed_grid')
                self.assertEqual((proof['start'], proof['end']), (str(sl.TRAIN[0]), str(sl.HOLDOUT[1])))
                self.assertEqual(proof['coverage_windows'], ['train', 'validation', 'holdout'])
                self.assertTrue(proof['forward_excluded'])
                self.assertIn('forward', proof['image_spec']['windows'])
                self.assertEqual(proof['image_spec']['roots'], ['PLTR', 'SPY'])
                self.assertEqual(proof['source_box_id'], 'sb_data')
                self.assertTrue(proof['verified_at'])
                return {'source_evidence': proof}
            with patch.object(images, 'build', build):
                ops.build('gate', 'candidate', sip_receipt=sha)


class CalibrationBinding(unittest.TestCase):
    def test_repeated_partial_finishes_and_lost_final_ack_keep_original_pair_binding(self):
        import calibration
        from contextlib import ExitStack
        blob = json.dumps({'source': 'league.gym.calibrate', 'hazard': {'SPY|q0|s|d0|k0|t0': 0.1},
                           'meta': {'fitted_on': {'days': 2, 'prints': 20}}}).encode()
        held = [False]
        class Lease:
            def __init__(self, api, box): self_box.assertEqual(box, 'sb_data')
            def __enter__(self): held[0] = True; return self
            def __exit__(self, *args): held[0] = False
            def check(self): self_box.assertTrue(held[0])
        class API:
            def __init__(self): self.files = {}
            def get(self, box): return {'status': 'running'}
            def egress(self, box): return {'document': {'no_network': True}}
            def exec(self, *args, **kwargs):
                result = SimpleNamespace(ok=True)
                result.check = lambda: result
                return result
            def upload(self, box, path, value, **kwargs): self.files[box, path] = value
            def download(self, box, path, **kwargs): return self.files[box, path]
            def sleep(self, box): pass
        self_box = self
        with tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)), ExitStack() as stack:
            state = Path(tmp)
            bl.write_json(bl.DATA_BOX, {'box_id': 'sb_data'})
            version = 'candidate-sip2-' + 'a' * 12
            initial = {}
            for kind in ('gym', 'gate'):
                initial[kind] = {'current': {'box_id': 'sb_' + kind, 'checkpoints': ['old-' + kind, 'old-backup-' + kind],
                    'version': version, 'roots': ['SPY'], 'windows': list(images.KINDS[kind]['keep']),
                    'source_evidence': {'source_box_id': 'sb_data', 'sip_receipt': 'a' * 64,
                                        'verified_at': '2026-09-30T06:00:00Z'}}}
            bl.write_json(bl.IMAGES, initial)
            pair = {k: {key: e['current'][key] for key in ('box_id', 'checkpoints', 'source_evidence', 'roots', 'windows')}
                    for k, e in initial.items()}
            ops = object.__new__(complete.Operations)
            ops.state, ops.api, ops.data = state, API(), SimpleNamespace(box_id='sb_data')
            calls = {'fit': 0, 'gym': 0, 'gate': 0}
            def fit(api, entry):
                self.assertTrue(held[0])
                calls['fit'] += 1
                return blob, 'engine-test'
            def finish(kind, box, **kwargs):
                kwargs['lease'].check()
                calls[kind] += 1
                if kind == 'gate' and calls[kind] <= 2:
                    raise RuntimeError('injected gate checkpoint outage')
                entries = bl.read_json(bl.IMAGES)
                entry = entries[kind]['current']
                entry.update(version=kwargs['version'], checkpoints=[f'{kind}-{calls[kind]}-a', f'{kind}-{calls[kind]}-b'])
                bl.write_json(bl.IMAGES, entries)
                return entry
            lost = [True]
            write = bl.write_json
            def write_lost_ack(path, value):
                write(path, value)
                if path.name == 'calibration.json' and lost[0]:
                    lost[0] = False
                    raise ConnectionError('lost final acknowledgement')
            stack.enter_context(patch.object(bl, 'RemoteLease', Lease))
            stack.enter_context(patch.object(calibration, 'fit_on_gym', fit))
            stack.enter_context(patch.object(images, 'finish', finish))
            stack.enter_context(patch('league.gym.driver.build_bundle', return_value=(b'', 'engine-test')))
            stack.enter_context(patch.object(bl, 'write_json', write_lost_ack))
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'checkpoint outage'):
                    ops.calibrate(version + '-calibrated', sip_receipt='a' * 64, pair=pair)
            with self.assertRaisesRegex(ConnectionError, 'final acknowledgement'):
                ops.calibrate(version + '-calibrated', sip_receipt='a' * 64, pair=pair)
            result = ops.calibrate(version + '-calibrated', sip_receipt='a' * 64, pair=pair)
            self.assertEqual(calls, {'fit': 3, 'gym': 3, 'gate': 3})
            self.assertEqual(result['pair_binding']['input_pair'], pair)
            self.assertEqual(result['templates'], {'gym': 'sb_gym', 'gate': 'sb_gate'})
            self.assertEqual(result['checkpoints'], {'gym': ['gym-3-a', 'gym-3-b'], 'gate': ['gate-3-a', 'gate-3-b']})
            self.assertEqual(result['train_checkpoint'], 'gym-2-a')
            self.assertEqual(result['roots'], ['SPY'])

    def test_replaced_pair_or_checkpoint_is_rejected_inside_lease_before_any_fit(self):
        import calibration
        for field, value in (('box_id', 'sb_replacement'), ('checkpoints', ['unbound-a', 'unbound-b']),
                             ('roots', ['SPY', 'PLTR'])):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)):
                state = Path(tmp)
                bl.write_json(bl.DATA_BOX, {'box_id': 'sb_data'})
                version = 'candidate-sip2-' + 'a' * 12
                initial = {k: {'current': {'box_id': 'sb_' + k, 'checkpoints': ['old-' + k, 'backup-' + k],
                    'version': version, 'roots': ['SPY'], 'windows': list(images.KINDS[k]['keep']),
                    'source_evidence': {'sip_receipt': 'a' * 64, 'source_box_id': 'sb_data'}}} for k in ('gym', 'gate')}
                pair = {k: {key: copy.deepcopy(e['current'][key]) for key in
                             ('box_id', 'checkpoints', 'source_evidence', 'roots', 'windows')} for k, e in initial.items()}
                bl.write_json(bl.IMAGES, initial)
                ops = object.__new__(complete.Operations)
                ops.state, ops.data = state, SimpleNamespace(box_id='sb_data')
                ops.api = SimpleNamespace(get=lambda _: {'status': 'running'})
                # Simulate replacement as the calibration lease is acquired, after any outer reads.
                class Lease:
                    def __enter__(self):
                        entries = bl.read_json(bl.IMAGES)
                        entries['gym']['current'][field] = value
                        bl.write_json(bl.IMAGES, entries)
                        return self
                    def __exit__(self, *args): pass
                    def check(self): pass
                with patch.object(bl, 'RemoteLease', return_value=Lease()), patch.object(calibration, 'fit_on_gym') as fit:
                    with self.assertRaisesRegex(RuntimeError, 'bound|checkpoint changed'):
                        ops.calibrate(version + '-calibrated', sip_receipt='a' * 64, pair=pair)
                    fit.assert_not_called()
