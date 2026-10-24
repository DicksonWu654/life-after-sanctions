"""Regression checks for publication, claim diffs, and event-retention boundaries."""
import csv
import datetime as dt
import json
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.lib.pipeline_io import Generation, write_json, atomic_publish
from scripts.pipeline import ROOT, Runner, export_step, findings_check, json_path
from scripts.export_site import Exporter, fit_budget, publication_lag
from scripts.lib import published_inputs

class PipelineChecks(unittest.TestCase):
    def test_bulk_publication_shares_immutable_inode_and_survives_stage_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);src=directory/'stage.csv';dst=directory/'published.csv'
            with src.open('wb') as f:f.truncate(20_000_001)
            dst.write_bytes(b'previous')
            atomic_publish(src,dst)
            self.assertEqual(src.stat().st_ino,dst.stat().st_ino)
            src.unlink()
            self.assertEqual(dst.stat().st_size,20_000_001)

    def test_flow_resume_releases_only_staged_csv_and_check_keeps_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);root=directory/'generation'
            (root/'scripts/analysis').mkdir(parents=True)
            (root/'data/derived').mkdir(parents=True)
            published=directory/'published.csv';published.write_text('published evidence')
            staged=root/'data/derived/flows_edges.csv'
            staged.hardlink_to(published)
            script=root/'scripts/analysis/flows.py'
            script.write_text('from pathlib import Path\nimport sys\np=Path("data/derived/flows_edges.csv")\nassert p.exists() == ("--check" in sys.argv)\n')
            command=[sys.executable,'-S','-B',str(ROOT/'scripts/lib/run_step.py'),str(root),'offline','scripts/analysis/flows.py','--resume']
            result=subprocess.run(command,cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(published.read_text(),'published evidence')
            staged.hardlink_to(published)
            result=subprocess.run(command+['--check'],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(staged.read_text(),'published evidence')

    def test_export_timeout_restores_signal_state(self):
        handler=signal.getsignal(signal.SIGALRM)
        runner=Runner(timeout=.02)
        with patch.object(runner,'say'), patch('scripts.pipeline.export',side_effect=lambda:time.sleep(1)):
            with self.assertRaisesRegex(TimeoutError,'Export timed out'):
                export_step(runner)
        self.assertEqual(signal.getsignal(signal.SIGALRM),handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))

    def test_materialize_result_namespace_preserves_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'site/data').mkdir(parents=True)
            original=root/'results/example.json'
            write_json(original,{'value':1})
            with Generation(root) as gen:
                staged=gen.root/'results/example.json'
                self.assertTrue(staged.is_symlink())
                gen.writable('results')
                self.assertFalse(staged.is_symlink())
                self.assertTrue(staged.resolve().is_relative_to(gen.root))
                write_json(staged,{'value':2})
                self.assertEqual(json.loads(original.read_text()),{'value':1})
                for invalid in ('../results',str(root/'results'),'.'):
                    with self.assertRaises(ValueError): gen.writable(invalid)
            self.assertEqual(json.loads(original.read_text()),{'value':1})

    def test_publication_day_proxy_is_not_before_evidence(self):
        point,bounds=publication_lag('2022-04-22',-.2)
        self.assertIsNone(point)
        self.assertLess(bounds[0],0)
        self.assertGreater(bounds[1],0)
        self.assertIsNone(publication_lag('2026-11-01',-.53)[0])
        self.assertEqual(publication_lag('2022-04-22',3)[0],3)

    def test_shared_coverage_preserves_other_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'docs').mkdir()
            (root/'site/data').mkdir(parents=True)
            doc=root/'docs/COVERAGE.md'
            doc.write_text('# Coverage\n<!-- freezes:start -->\nold\n<!-- freezes:end -->\n')
            with Generation(root) as gen:
                gen.writable('docs/COVERAGE.md')
                (gen.root/'docs/COVERAGE.md').write_text(doc.read_text().replace('old','new'))
                doc.write_text(doc.read_text()+'\nConcurrent process section\n')
                gen.publish()
            self.assertIn('new',doc.read_text())
            self.assertIn('Concurrent process section',doc.read_text())

    def test_published_snapshot_survives_live_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'site/data').mkdir(parents=True)
            (root/'results').mkdir()
            write_json(root/'results/example.json',{'value':1})
            original=root/'data/timelines/btc/example.json'
            write_json(original,{'old':True})
            work=root/'scripts/lib/.pipeline-work'
            with patch.multiple(published_inputs,ROOT=root,WORK=work,POINTER=work/'published-inputs.json'):
                with Generation(root) as gen:
                    gen.snapshot('data/timelines')
                    info=published_inputs.retain(gen)
                write_json(original,{'new':True})
                self.assertEqual(published_inputs.current()['path'],info['path'])
                saved=root/info['path']/'timelines/btc/example.json'
                self.assertEqual(json.loads(saved.read_text()),{'old':True})
                saved.write_text('{"tampered":true}')
                with self.assertRaisesRegex(ValueError,'snapshot changed'): published_inputs.current()

    def test_discard_publish_and_concurrent_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'data').mkdir()
            (root/'site/data').mkdir(parents=True)
            (root/'data/example.csv').write_text('original')
            with Generation(root) as gen:
                gen.writable('data/example.csv')
                (gen.root/'data/example.csv').write_text('failed source partial')
            self.assertEqual((root/'data/example.csv').read_text(),'original')
            with Generation(root) as gen:
                gen.writable('data/example.csv')
                (gen.root/'data/example.csv').write_text('successful')
                gen.publish()
            self.assertEqual((root/'data/example.csv').read_text(),'successful')
            with Generation(root) as gen:
                gen.writable('data/example.csv')
                (gen.root/'data/example.csv').write_text('pipeline')
                (root/'data/example.csv').write_text('concurrent process')
                with self.assertRaisesRegex(RuntimeError,'Concurrent writer'): gen.publish()
            self.assertEqual((root/'data/example.csv').read_text(),'concurrent process')

    def test_claim_mutation_and_paths(self):
        self.assertEqual(json_path({'a':[{'b':2}]},'a[0].b'),2)
        self.assertEqual(json_path({'a/b':3},'/a~1b'),3)
        actual=json.loads((ROOT/'results/checkpoints.json').read_text())['coverage']['ledger_addresses']['value']
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'FINDINGS.md'
            p.write_text(f'{actual:,} addresses. <!-- check: results/checkpoints.json#coverage.ledger_addresses -->')
            self.assertEqual(findings_check(p)['tagged_values'],1)
            p.write_text(f'{actual:,} addresses.\n<!-- check: results/checkpoints.json#coverage.ledger_addresses.value = {actual} -->')
            self.assertEqual(findings_check(p)['tagged_values'],1)
            p.write_text(f'{actual+1:,} addresses. <!-- check: results/checkpoints.json#coverage.ledger_addresses -->')
            with self.assertRaisesRegex(RuntimeError,'does not match'): findings_check(p)
            p.write_text('1. 999 rows. <!-- check: results/checkpoints.json#schema_version -->')
            with self.assertRaisesRegex(RuntimeError,'does not match'): findings_check(p)
            flows=json.loads((ROOT/'results/flows.json').read_text())
            usd=flows['summary']['wallet_outflows_usd']['value']
            p.write_text(f'{usd/1e9:.3f} billion USD. <!-- check: results/flows.json#summary.wallet_outflows_usd.value -->')
            self.assertEqual(findings_check(p)['tagged_values'],1)
            for i,f in enumerate(flows['findings']):
                if f.get('amount',{}).get('unit')=='share':
                    p.write_text(f"{f['amount']['value']*100:.3f}%. <!-- check: results/flows.json#findings[{i}].amount.value -->")
                    self.assertEqual(findings_check(p)['tagged_values'],1)
                    break

    def test_offline_child_denies_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'scripts/probe.py').write_text('import socket\nsocket.getaddrinfo("example.com",443)\n')
            run=subprocess.run([sys.executable,'-S','-B',str(ROOT/'scripts/lib/run_step.py'),str(root),'offline','scripts/probe.py'],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('OFFLINE_NETWORK_DENIED',run.stderr)

    def test_raw_copy_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            (root/'site/data').mkdir(parents=True)
            original=root/'data/raw/source/cache.json'
            original.parent.mkdir(parents=True)
            original.write_text('saved evidence')
            (root/'scripts/writer.py').write_text('from pathlib import Path\nPath("data/raw/source/cache.json").write_text("failed partial write")\nraise SystemExit(1)\n')
            with Generation(root) as gen:
                gen.writable('data/raw/source')
                run=subprocess.run([sys.executable,'-S','-B',str(ROOT/'scripts/lib/run_step.py'),str(gen.root),'offline','scripts/writer.py'],cwd=gen.root,capture_output=True,text=True)
                self.assertEqual(run.returncode,1,run.stderr)
                self.assertEqual((gen.root/'data/raw/source/cache.json').read_text(),'failed partial write')
                self.assertEqual(original.read_text(),'saved evidence')

    def test_newest_plus_window_plus_old_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'data').mkdir()
            def table(path,records):
                path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('w') as f:
                    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
            row={'chain':'BTC','address':'synthetic','address_normalized':'synthetic','trackable':'true',
                 'first_listed_date':'2020-01-01','listed_date':'2020-01-01','listed_action_url':'https://example.com/action',
                 'listed_raw_ref':'raw','listing_events':'[]','sdn_uid':'1','sdn_name':'SYNTHETIC','ticker':'BTC',
                 'programs':'TEST','delisted_date':'','raw_ref':'raw','source_url':'https://example.com/source'}
            row['sdn_uids']='1'
            # Explicit address-table UIDs survive a missing exact chain join.
            table(root/'data/ledger.csv',[dict(row,chain='ETH')])
            txs=[{'time_utc':(dt.datetime(2021,1,1,tzinfo=dt.timezone.utc)+dt.timedelta(minutes=i)).isoformat(),
                  'direction':'in','asset':'BTC','amount':'1','hash':str(i)} for i in range(2100)]
            txs.insert(0,{'time_utc':'2020-01-02T00:00:00Z','direction':'out','asset':'BTC','amount':'1','hash':'protected'})
            write_json(root/'data/timelines/btc/synthetic.json',{'chain':'btc','address':'synthetic','coverage':{'complete':True},'txs':txs,'balance_now':[]})
            freeze={'chain':'BTC','address':'synthetic','address_normalized':'synthetic','token':'USDT','event':'AddedBlackList',
                    'timestamp':'2010-01-01T00:00:00Z','block':'1','log_index':'0','balance_at_freeze':'','tx_hash':'freeze',
                    'source_url':'https://example.com/freeze','raw_ref':'raw'}
            table(root/'data/freezes.csv',[freeze])
            out=root/'export'
            ex=Exporter(root,out)
            # An explicitly untrackable source can have an empty checkpoint
            # record; retain all six unknown slots rather than dropping them.
            ex.checkpoint_rows[('btc','synthetic')] = {
                'checkpoints':'{}','reconciliation':'{}','examples':'{}'}
            ex.detail(row)
            detail=json.loads((out/'address/btc/synthetic.json').read_text())
            hashes={e.get('tx') for e in detail['events']}
            self.assertIn('protected',hashes)
            self.assertIn('freeze',hashes)
            self.assertNotIn('0',hashes)
            self.assertTrue(detail['truncation']['truncated'])
            self.assertEqual(detail['truncation']['retained_transfer_events'],2000)
            self.assertEqual(sum(c.get('in',0)+c.get('out',0) for c in detail['monthly_counts']),2101)
            self.assertEqual(len(detail['checkpoints']),6)
            self.assertEqual(detail['entities'],[{'uid':'1','name':'SYNTHETIC'}])
            self.assertTrue(any(e['kind']=='designation' for e in detail['events']))
            write_json(out/'meta.json',{'export_counts':{'files':2,'bytes_before_meta':0}})
            before=sum(p.stat().st_size for p in out.rglob('*.json'))
            after=fit_budget(out,budget=before-5_000)
            compact=json.loads((out/'address/btc/synthetic.json').read_text())
            compact_hashes={e.get('tx') for e in compact['events']}
            self.assertLess(after,before-5_000)
            self.assertIn('protected',compact_hashes)
            self.assertIn('freeze',compact_hashes)
            self.assertTrue(compact['truncation']['budget_limited'])

if __name__=='__main__': unittest.main()
