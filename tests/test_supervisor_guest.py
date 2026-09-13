import gzip,hashlib,json,signal,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch, call
from portfolio_runtime import supervisor_guest as g
class BackupTests(unittest.TestCase):
 def test_five_day_market_receipts_pack_restore_and_reuse_confirmed_objects(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state/market').mkdir(parents=True)
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'host-manifest.json').write_text('{}')
   originals={}
   # 120 hourly epochs x 50 price/metadata receipts exceeds the former
   # 4,000-file cap without requiring large, synthetic research databases.
   for day in range(14,19):
    for hour in range(24):
     for index in range(25):
      name=f'S{index}-202609{day}T{hour:02d}0000Z-{index:016x}'
      for suffix,body in (('.json',{'price':index+hour+1,'source':'saved exact response'}),
                          ('.meta.json',{'captured_at':f'2026-09-{day}T{hour:02d}:00:00Z'})):
       path=Path('state/market')/(name+suffix);raw=json.dumps(body).encode();(root/path).write_bytes(raw);originals[str(path)]=raw
   uploaded={};calls=[]
   def uploader(url,path,h):
    raw=path.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),h);uploaded[url]=raw;calls.append(url)
   first=g.backup(root,uploader=uploader);manifest=json.loads(uploaded[next(k for k in calls if k.endswith('.json'))])
   bundles=[row for row in manifest['files'] if row.get('format')=='market-receipts-v1']
   self.assertEqual(len(bundles),5);self.assertEqual(sum(r['members'] for r in bundles),6000)
   self.assertLess(first['files'],10)
   restored=root/'restored';restored.mkdir()
   for row in bundles:
    packed=next(raw for key,raw in uploaded.items() if key.endswith(row['object_key']))
    raw=gzip.decompress(packed);self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
    archive=root/Path(row['path']).name;archive.write_bytes(raw)
    self.assertEqual(g.restore_market_receipts(archive,restored)['restored_market_receipts'],row['members'])
    self.assertEqual(g.restore_market_receipts(archive,restored)['restored_market_receipts'],row['members'])
   self.assertEqual({str(p.relative_to(restored)):p.read_bytes() for p in (restored/'state/market').iterdir()},originals)
   calls.clear()
   with patch.object(g.gzip,'GzipFile',wraps=g.gzip.GzipFile) as compress:
    second=g.backup(root,uploader=uploader)
    self.assertLessEqual(compress.call_count,1) # Unchanged source hashes bypass repeated compression too.
   later=json.loads(uploaded[next(k for k in calls if k.endswith('.json'))])
   self.assertNotEqual(first['manifest_key'],second['manifest_key'])
   self.assertEqual([r['object_key'] for r in later['files'] if r.get('format')=='market-receipts-v1'],[r['object_key'] for r in bundles])
   self.assertLessEqual(len(calls),2) # Changed health + manifest; all original receipts reuse R2 objects.

 def test_unconfirmed_upload_is_retried_and_bundle_restore_rejects_tampering(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state/market').mkdir(parents=True)
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'state/market/AAPL-20260914T120000Z-0000000000000000.json').write_text('{"price":1}')
   calls=[]
   def uncertain(url,path,h):calls.append(h);raise OSError('receipt missing')
   with self.assertRaises(OSError):g.backup(root,uploader=uncertain)
   with closing(sqlite3.connect(root/'state/.backup-uploads.sqlite')) as db:self.assertEqual(db.execute('SELECT count(*) FROM uploads').fetchone()[0],0)
   uploads={}
   def uploader(url,path,h):uploads[url]=path.read_bytes()
   g.backup(root,uploader=uploader)
   self.assertTrue(any(hashlib.sha256(raw).hexdigest()==calls[0] for raw in uploads.values()))
   manifest=json.loads(next(raw for url,raw in uploads.items() if url.endswith('.json')))
   row=next(r for r in manifest['files'] if r.get('format')=='market-receipts-v1')
   archive=root/'archive.sqlite';archive.write_bytes(gzip.decompress(next(raw for url,raw in uploads.items() if url.endswith(row['object_key']))))
   with closing(sqlite3.connect(archive)) as db,db:db.execute("UPDATE receipts SET payload=?",(b'{"price":2}',))
   with self.assertRaisesRegex(ValueError,'bundle_integrity_failed'):g.restore_market_receipts(archive,root/'restore')

 def test_complete_daily_packet_restores_every_company_without_redundant_uploads(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state').mkdir()
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'host-manifest.json').write_text('{}')
   complete=root/'state/evidence/2026-09-13';partial=root/'state/evidence/2026-09-14'
   records=[{'symbol':symbol,'cik':str(i).zfill(10),'captured_at':'2026-09-13T19:00:00Z',
             'facts':{'cash':[{'tag':'CashAndCashEquivalentsAtCarryingValue','unit':'USD',
                              'observations':[{'val':100+i,'end':'2026-06-30'}]}]}}
            for i,symbol in enumerate(('AAPL','MSFT','NVDA'),1)]
   packet={'companies':records,'universe':{'companies':[{'symbol':r['symbol']} for r in records]}}
   for day in (complete,partial):
    (day/'companies').mkdir(parents=True)
    for record in records:(day/'companies'/f"{record['symbol']}.json").write_text(json.dumps(record))
    (day/'universe.json').write_text(json.dumps(packet['universe']))
    (day/'capture.json').write_text(json.dumps({'captured':len(records)}))
   (complete/'evidence.json').write_text(json.dumps(packet))
   epoch=root/'state/epochs/rehearsal-00';epoch.mkdir(parents=True)
   (epoch/'evidence.json').write_text(json.dumps(packet))
   uploaded={}
   def uploader(url,path,hash_value):uploaded[url]=path.read_bytes()
   g.backup(root,uploader=uploader)
   manifest=json.loads(next(data for url,data in uploaded.items() if url.endswith('.json')))
   files={item['path']:item for item in manifest['files']}
   for record in records:
    self.assertNotIn(f"state/evidence/2026-09-13/companies/{record['symbol']}.json",files)
    self.assertIn(f"state/evidence/2026-09-14/companies/{record['symbol']}.json",files)
   for name in ('state/evidence/2026-09-13/evidence.json','state/evidence/2026-09-13/universe.json',
                'state/evidence/2026-09-13/capture.json','state/epochs/rehearsal-00/evidence.json'):
    self.assertIn(name,files)
   item=files['state/evidence/2026-09-13/evidence.json']
   raw=gzip.decompress(next(data for url,data in uploaded.items() if url.endswith(item['object_key'])))
   self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
   self.assertEqual(json.loads(raw)['companies'],records)

 def test_incomplete_or_changed_assembled_company_records_never_hide_cache_files(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);day=root/'state/evidence/2026-09-13';(day/'companies').mkdir(parents=True)
   path=day/'companies/AAPL.json';record={'symbol':'AAPL','facts':{'cash':100}}
   path.write_text(json.dumps(record))
   for packet in ({'companies':[record],'universe':{'companies':[{'symbol':'AAPL'},{'symbol':'MSFT'}]}},
                  {'companies':[{'symbol':'AAPL','facts':{'cash':99}}],'universe':{'companies':[{'symbol':'AAPL'}]}}):
    (day/'evidence.json').write_text(json.dumps(packet))
    self.assertIn(path,g.artifact_paths(root))
   (day/'evidence.json').write_text('{unfinished')
   self.assertIn(path,g.artifact_paths(root))

 def test_snapshots_are_checked_and_manifest_committed_after_artifacts(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state').mkdir()
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'host-manifest.json').write_text('{}')
   with closing(sqlite3.connect(root/'state/paper.sqlite')) as db, db:db.execute('create table events(id integer primary key,value text)');db.execute("insert into events(value)values('saved')")
   (root/'state/credentials.env').write_text('secret must not be copied')
   (root/'state/raw').mkdir();(root/'state/raw/not-backed-up.json').write_text('{}')
   rows=[]
   def uploader(url,path,h):
    data=path.read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),h);rows.append((url,data))
   result=g.backup(root,uploader=uploader)
   self.assertEqual(result['status'],'complete');self.assertTrue(rows[-1][0].endswith('.json'))
   manifest=json.loads(rows[-1][1]);names={x['path'] for x in manifest['files']}
   self.assertIn('state/paper.sqlite',names);self.assertNotIn('state/credentials.env',names);self.assertNotIn('state/raw/not-backed-up.json',names)
   self.assertFalse(manifest['consistent_across_databases'])
 def test_failed_upload_does_not_claim_a_completed_snapshot(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'config').mkdir();(root/'state').mkdir()
   (root/'config/run.json').write_text(json.dumps({'service_id':'week-20260914','backup_url':'https://portfolio-supervisor.example.workers.dev/v1/backups'}))
   (root/'host-manifest.json').write_text('{}')
   def failing(*args):raise OSError('network')
   with self.assertRaises(OSError):g.backup(root,uploader=failing)
   state=json.loads((root/'state/backup-health.json').read_text());self.assertEqual(state['status'],'failed');self.assertNotIn('manifest_key',state)
class ForceStopTests(unittest.TestCase):
 def test_only_verified_bootstrap_and_its_exact_service_child_can_be_killed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'state').mkdir();proc=root/'test-proc'
   boot=proc/'sys/kernel/random';boot.mkdir(parents=True);(boot/'boot_id').write_text('current-boot')
   def process(pid,ppid,args):
    p=proc/str(pid);p.mkdir();(p/'status').write_text(f'Name: python3\nPPid:\t{ppid}\n');(p/'cmdline').write_bytes(b'\0'.join(args)+b'\0')
   process(100,1,[b'python3',b'/workspace/host-boot.py'])
   process(101,100,[b'python3',b'-m',b'portfolio_runtime.service',b'run'])
   process(102,99,[b'python3',b'-m',b'portfolio_runtime.service',b'run'])
   process(103,100,[b'python3',b'-m',b'unrelated_service'])
   (root/'state/host-process.json').write_text(json.dumps({'pid':100,'boot_id':'current-boot'}))
   real_path=Path
   def mapped_path(value):
    value=str(value)
    return proc/value.removeprefix('/proc/').lstrip('/') if value.startswith('/proc/') else proc if value=='/proc' else real_path(value)
   with patch.object(g,'Path',side_effect=mapped_path),patch.object(g.os,'kill') as kill:
    self.assertEqual(g.force_stop(root),{'stopped':True})
    self.assertEqual(kill.call_args_list,[call(101,signal.SIGKILL),call(100,signal.SIGKILL)])

 def test_stale_boot_reserved_pid_or_changed_command_denies_before_any_signal(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'state').mkdir();proc=root/'test-proc';boot=proc/'sys/kernel/random';boot.mkdir(parents=True)
   (boot/'boot_id').write_text('current-boot');parent=proc/'100';parent.mkdir();(parent/'cmdline').write_bytes(b'python3\0unrelated.py\0')
   real_path=Path
   def mapped_path(value):
    value=str(value)
    return proc/value.removeprefix('/proc/').lstrip('/') if value.startswith('/proc/') else proc if value=='/proc' else real_path(value)
   for saved in [{'pid':1,'boot_id':'current-boot'},{'pid':True,'boot_id':'current-boot'},{'pid':100,'boot_id':'old-boot'},{'pid':100,'boot_id':'current-boot'}]:
    (root/'state/host-process.json').write_text(json.dumps(saved))
    with patch.object(g,'Path',side_effect=mapped_path),patch.object(g.os,'kill') as kill:
     with self.assertRaisesRegex(ValueError,'process_identity_changed'):g.force_stop(root)
     kill.assert_not_called()

if __name__=='__main__':unittest.main()
