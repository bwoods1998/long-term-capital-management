"""Research breadth is complete, but readiness needs actual historical file evidence."""
from __future__ import annotations

import copy
import datetime as dt
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

DATA = Path(__file__).resolve().parents[2] / 'scripts/data'
if str(DATA) not in sys.path:
    sys.path.insert(0,str(DATA))
import catalog as C


def asset(symbol='AAPL', **kw):
    return dict(symbol=symbol,status='active',tradable=True,exchange='NASDAQ',
                **{'class':'us_equity'},attributes=['has_options'],**kw)


def receipt(rows=None):
    return {'at':'2026-09-26T20:04:16+00:00',
            'responses':[{'path':C.ASSETS_PATH,'status':200,'body':rows or [asset()]}]}


def image(roots=None):
    return {'version':'full-calibrated','checkpoints':['cp-a','cp-b'], 'roots':roots or ['AAPL'],
            'sealed':{'no_network':True},'windows':['train','validation'],'gate_mark':False}


class Catalog(unittest.TestCase):
    def test_all_candidates_survive_and_nontradable_are_visible(self):
        rows = [asset('N'+chr(65+i//26)+chr(65+i%26)) for i in range(137)]
        rows[0]['tradable'] = False
        rows.append(asset('BRK.B'))
        result = C.plan(receipt(rows))
        self.assertEqual(result['summary']['assets'],138)
        self.assertEqual(result['summary']['observed_tradable_assets'],137)
        self.assertEqual(len(result['candidates']),138+len(C.INDICES))
        self.assertEqual(len(result['backlog']),len(result['candidates']))
        self.assertEqual(result['summary']['research_ready'],0)
        indexed = {r['root']:r for r in result['candidates']}
        self.assertIn('asset_not_currently_tradable',indexed[rows[0]['symbol']]['blockers'])
        self.assertIn('symbol_mapping_unverified',indexed['BRK.B']['blockers'])
        self.assertFalse(indexed['DJXW']['venue']['rules_implemented'])
        self.assertEqual(indexed['VIXW']['venue']['settlement'],'AM')
        self.assertTrue(all(not r['paper_ready'] and not r['live_ready'] for r in result['candidates']))

    def test_actual_attribute_spelling_and_late_close_are_retained(self):
        a = asset()
        a['attributes'] = ['has_options','options_late_close']
        self.assertTrue(C.assets(receipt([a]))['AAPL']['late_close'])
        a['attributes'] = ['options_enabled']
        self.assertTrue(C.assets(receipt([a]))['AAPL']['optionable'])
        a['attributes'] = ['fractional_eh_enabled']
        with self.assertRaises(C.CatalogError):
            C.assets(receipt([a]))

    def test_invalid_discovery_is_not_an_empty_ready_catalog(self):
        cases = []
        for key,value in [('status',500),('path','v2/assets'),('body',{})]:
            r = receipt(); r['responses'][0][key] = value; cases.append(r)
        r = receipt(); r['at'] = '2026-09-26T20:04:16'; cases.append(r)
        r = receipt(); r['responses'][0]['body'][0]['tradable'] = 'true'; cases.append(r)
        a,b = asset(),asset(); b['tradable'] = False
        cases.append(receipt([a,b]))
        for r in cases:
            with self.subTest(r=r), self.assertRaises((ValueError,TypeError)):
                C.plan(r)

    def test_backlog_priority_does_not_drop_the_tail_and_preview_says_what_is_missing(self):
        result = C.plan(receipt([asset('AAPL'),asset('NVDA'),asset('MSFT')]),priority_roots=['NVDA'])
        self.assertEqual(result['backlog'][0]['root'],'NVDA')
        prompt = C.prompt_context(result,backlog_limit=2)
        self.assertEqual(len(prompt['backlog_preview']),2)
        self.assertEqual(prompt['backlog_total'],10)
        self.assertEqual(prompt['backlog_omitted'],8)
        self.assertEqual(prompt['ready_roots'],{})
        self.assertNotIn('exchange',json.dumps(prompt))

    def test_discover_is_only_one_get_and_never_outputs_the_token(self):
        class Response(io.BytesIO):
            status=200
        class Opener:
            requests=[]
            def open(self,request,timeout):
                self.requests.append(request)
                return Response(json.dumps([asset()]).encode())
        opener=Opener()
        r=C.discover('https://gateway.invalid','CANARY_SECRET',opener=opener,at='2026-09-26T20:04:16Z')
        self.assertEqual(len(opener.requests),1)
        self.assertEqual(opener.requests[0].get_method(),'GET')
        self.assertEqual(opener.requests[0].full_url,'https://gateway.invalid/v1/alpaca/'+C.ASSETS_PATH)
        self.assertNotIn('CANARY_SECRET',json.dumps(r))
        self.assertIsNone(C.NoRedirect().redirect_request(None,None,None,None,None,None))
        with self.assertRaises(C.CatalogError):
            C.discover('https://user:secret@gateway.invalid','CANARY_SECRET',opener=opener)

    def test_failed_cli_prints_only_error_type_not_private_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            (path/'bad.json').write_text('CANARY_PRIVATE_BROKER_BODY')
            with patch('builtins.print') as output:
                code=C.main(['plan','--assets-receipt',str(path/'bad.json'),'--out',str(path/'out.json')])
            self.assertEqual(code,1)
            self.assertNotIn('CANARY_PRIVATE',str(output.call_args_list))
            self.assertFalse((path/'out.json').exists())

    def test_private_outputs_and_offline_cli_never_dispatch_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            C.private_write(path/'assets.json',receipt())
            with patch.object(C,'discover',side_effect=AssertionError('network')), patch('builtins.print'):
                code=C.main(['plan','--assets-receipt',str(path/'assets.json'),'--out',str(path/'catalog.json'),
                             '--prompt-out',str(path/'prompt.json')])
            self.assertEqual(code,0)
            self.assertEqual(stat.S_IMODE((path/'catalog.json').stat().st_mode),0o600)
            result=json.loads((path/'catalog.json').read_text())
            self.assertEqual(result['actions'],{'data_jobs_started':0,'settings_changed':False,'trading_authorized':False})


try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    pa=pq=None


@unittest.skipUnless(pa is not None,'optional parquet dependency is unavailable')
class Coverage(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Path(self.tmp.name)/'store'
        self.store.mkdir()
        self.windows={'train':['2024-01-02','2024-01-03'],'validation':['2025-01-02','2025-01-03']}
        self.calendar={'years':[2024,2025],'exceptions':{}}
        self.rows=[]
        days=[r[0] for values in C.sessions(self.calendar,self.windows).values() for r in values]
        expiries=[]
        for day in days:
            d=dt.date.fromisoformat(day)
            # Source requested0-14; actual quotes omit a listed 12DTE contract.
            self.write('nbbo',day,[{'expiration':d+dt.timedelta(days=5),'minute':570,'bid':1.0,'ask':1.1}],
                       'thetadata option_history_quote 1m exp=* max_dte=14 strike_range=25')
            self.write('underlying',day,[{'minute':570,'price':100.0}],C.SIP_SOURCE)
            expiries.extend({'root':'AAPL','date':d,'expiration':d+dt.timedelta(days=n)} for n in (5,12,25))
        (self.store/'VERSION').write_text('store-v1\n')
        pq.write_table(pa.Table.from_pylist([{'date':dt.date.fromisoformat(d),'open_min':570,'close_min':960} for d in days]),
                       self.store/'calendar.parquet')
        pq.write_table(pa.Table.from_pylist(expiries),self.store/'expiries.parquet')
        self.flush()

    def write(self,kind,day,rows,source):
        path=self.store/kind/'AAPL'/(day+'.parquet')
        path.parent.mkdir(parents=True,exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows),path)
        window='train' if day.startswith('2024') else 'validation'
        self.rows=[r for r in self.rows if not(r['kind']==kind and str(r['date'])==day)]
        self.rows.append({'root':'AAPL','kind':kind,'date':dt.date.fromisoformat(day),'window':window,'rows':len(rows),
                          'bytes':path.stat().st_size,'sha256':C.digest(path),'source':source})

    def flush(self):
        pq.write_table(pa.Table.from_pylist(self.rows),self.store/'manifest.parquet')

    def audit(self):
        return C.audit_store(self.store,self.calendar,image(),'cp-a',windows=self.windows)

    def result(self,proof):
        return C.plan(receipt(),coverage=proof,image=image(),checkpoint='cp-a',windows=self.windows)

    def test_only_file_verified_horizon_is_ready_not_listings_or_request_range(self):
        before={p: p.stat().st_mtime_ns for p in self.store.rglob('*') if p.is_file()}
        with patch('socket.socket',side_effect=AssertionError('network')):
            proof=self.audit()
        row=next(r for r in self.result(proof)['candidates'] if r['root']=='AAPL')
        self.assertTrue(row['research_ready'])
        self.assertEqual(row['data']['verified_horizons'],[[0,7]])
        self.assertEqual(row['data']['missing_horizons'],[[8,14],[15,45],[46,60]])
        self.assertEqual(before,{p:p.stat().st_mtime_ns for p in before})
        self.assertFalse(proof['quote_values_read'])
        self.assertNotIn('bid',json.dumps(proof))
        self.assertNotIn('price',json.dumps(proof))
        missing=row['data']['horizons'][1]['missing']
        self.assertIn('train:quoted_expiries_incomplete',missing)
        self.assertNotIn('train:collector_horizon_unverified',missing)
        self.assertIn('train:collector_horizon_unverified',row['data']['horizons'][2]['missing'])

    def test_verified_back_months_expand_the_prompt_without_clipping_ready_roots(self):
        for day in ('2024-01-02','2024-01-03','2025-01-02','2025-01-03'):
            d=dt.date.fromisoformat(day)
            self.write('nbbo',day,[{'expiration':d+dt.timedelta(days=n),'minute':570,'bid':1.0,'ask':1.1} for n in (5,12,25)],
                       'thetadata option_history_quote 1m max_dte=14 strike_range=25 + back months to 45 DTE by expiry')
        self.flush()
        prompt=C.prompt_context(self.result(self.audit()))
        self.assertEqual(prompt['ready_roots'],{'AAPL':[[0,45]]})
        self.assertNotIn('46',str(prompt['ready_roots']))

    def test_partial_window_and_wrong_underlying_source_do_not_become_ready(self):
        (self.store/'nbbo/AAPL/2025-01-03.parquet').unlink()
        row=next(r for r in self.result(self.audit())['candidates'] if r['root']=='AAPL')
        self.assertFalse(row['research_ready'])
        self.assertEqual(row['data']['windows']['validation']['nbbo_verified'],1)
        self.assertEqual(row['data']['verified_horizons'],[])
        for r in self.rows:
            if r['kind']=='underlying': r['source']='option underlying price only'
        self.flush()
        proof=self.audit()
        self.assertEqual(proof['roots']['AAPL']['train']['underlying_verified'],0)

    def test_content_hash_corruption_and_bool_counts_are_refused(self):
        p=self.store/'nbbo/AAPL/2024-01-02.parquet'
        p.write_bytes(p.read_bytes()+b'changed')
        proof=self.audit()
        self.assertFalse(next(r for r in self.result(proof)['candidates'] if r['root']=='AAPL')['research_ready'])
        proof['roots']['AAPL']['train']['expected']=True
        proof['receipt_sha256']=C.identity({k:v for k,v in proof.items() if k!='receipt_sha256'})
        self.assertFalse(next(r for r in self.result(proof)['candidates'] if r['root']=='AAPL')['research_ready'])

    def test_gate_and_mislabeled_holdout_are_refused_before_per_day_reads(self):
        (self.store/'GATE').write_text('gate')
        with patch.object(pq,'read_table',side_effect=AssertionError('no gate reads')),self.assertRaises(C.CatalogError):
            self.audit()
        (self.store/'GATE').unlink()
        self.rows[0]['window']='holdout'; self.flush()
        with patch.object(pq,'ParquetFile',side_effect=AssertionError('no per-day read')),self.assertRaises(C.CatalogError):
            self.audit()

    def test_custom_windows_cannot_relabel_a_holdout_as_train(self):
        for window,bounds in [('train',['2026-01-02','2026-01-03']),
                              ('validation',['2024-01-02','2025-01-03'])]:
            windows=dict(self.windows,**{window:bounds})
            with patch.object(pq,'read_table',side_effect=AssertionError('no store read')),self.assertRaises(C.CatalogError):
                C.audit_store(self.store,dict(self.calendar,years=[2024,2025,2026]),image(),'cp-a',windows=windows)

    def test_control_metadata_symlink_is_refused_before_any_parquet_read(self):
        path=self.store/'manifest.parquet'
        target=Path(self.tmp.name)/'elsewhere.parquet'
        path.rename(target); path.symlink_to(target)
        with patch.object(pq,'read_table',side_effect=AssertionError('no redirected read')),self.assertRaises(C.CatalogError):
            self.audit()

    def test_symlink_data_and_metadata_changed_during_audit_cannot_pass(self):
        file=self.store/'nbbo/AAPL/2024-01-02.parquet'
        moved=file.with_suffix('.retained')
        file.rename(moved); file.symlink_to(moved)
        self.assertEqual(self.audit()['roots']['AAPL']['train']['nbbo_verified'],1)
        original=C.digest
        seen=0
        def changing(path):
            nonlocal seen
            value=original(path)
            if path.name=='manifest.parquet':
                seen+=1
                if seen>1: return '0'*64
            return value
        with patch.object(C,'digest',side_effect=changing),self.assertRaises(C.CatalogError):
            self.audit()

    def test_calendar_mismatch_and_aggregate_only_image_are_not_coverage(self):
        self.calendar['exceptions']['2024-01-03']=None
        with self.assertRaises(C.CatalogError): self.audit()
        with self.assertRaises(C.CatalogError):
            C.plan(receipt(),coverage={'roots':['AAPL'],'first_date':'2022-01-03'},image=image(),checkpoint='cp-a')

    def test_proof_is_bound_to_exact_checkpoint_receipt_windows_and_code(self):
        proof=self.audit()
        for change in ({'checkpoint':'cp-b'},{'image':dict(image(),version='another')},{'windows':C.WINDOWS}):
            args={'coverage':proof,'image':image(),'checkpoint':'cp-a','windows':self.windows}; args.update(change)
            with self.subTest(change=change),self.assertRaises(C.CatalogError): C.plan(receipt(),**args)
        changed=copy.deepcopy(proof)
        changed['roots']['AAPL']['train']['nbbo_verified']=99
        with self.assertRaises(C.CatalogError): self.result(changed)
        changed=copy.deepcopy(proof); changed['audit_code_sha256']='a'*64
        changed['receipt_sha256']=C.identity({k:v for k,v in changed.items() if k!='receipt_sha256'})
        with self.assertRaises(C.CatalogError): self.result(changed)


if __name__=='__main__':
    unittest.main()
