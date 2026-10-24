import json,tempfile,unittest
from pathlib import Path
from scripts.lib.fetch_status import apply_status,prefix_metadata,report_status
from unittest.mock import patch
from scripts.lib.pipeline_io import Generation,write_json,read_json
import scripts.pipeline as pipeline

class StatusTests(unittest.TestCase):
    def test_completed_bounded_study_keeps_partial_history_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            (root/'data/FETCH_STATUS.json').write_text(json.dumps({'acquisition_complete':True,'chains':[{'chain':'trx','complete':False}],'issuer_history':{'complete':True}}))
            result=apply_status({'provisional':True,'cases':[{'provisional':True}],'coverage':{'all_pools_events_complete':True}},root,'cases')
            self.assertFalse(result['provisional']);self.assertFalse(result['cases'][0]['provisional'])
            self.assertFalse(result['fetch_status']['whole_history_complete_by_chain']['trx'])
            self.assertIn('provisional:false',report_status('`provisional:true`',result))
            self.assertEqual(report_status(b'`provisional:true`',result),b'`provisional:false`')
            result=apply_status({'coverage':{'all_pools_events_complete':False}},root,'tornado')
            self.assertTrue(result['provisional'])
    def test_missing_status_remains_provisional(self):
        with tempfile.TemporaryDirectory() as tmp:self.assertTrue(apply_status({},Path(tmp),'flows')['provisional'])
    def test_metadata_stops_before_bulk_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json';p.write_text('{"fetched_at":"2026-10-23T00:00:00Z","coverage":{"complete":false,"priority_windows_complete":true},"txs":['+' '*1_000_000)
            self.assertTrue(prefix_metadata(p)['coverage']['priority_windows_complete'])

    def test_success_survives_later_source_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write_json(root/'site/data/meta.json',{'last_refreshed_utc':'old','source_status':{'utxo':{'last_success_utc':'earlier'}}})
            with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'source_revision',return_value='revision'):
                pipeline.persist_source_status('ledger',{'stale':False,'last_success_utc':'new'})
                pipeline.persist_source_status('utxo',{'stale':True,'reason':'failed'})
            meta=read_json(root/'site/data/meta.json')
            self.assertFalse(meta['source_status']['ledger']['stale'])
            self.assertTrue(meta['source_status']['utxo']['stale'])
            self.assertEqual(meta['source_status']['utxo']['last_success_utc'],'earlier')
            self.assertEqual(meta['last_refreshed_utc'],'old')

    def test_utxo_privacy_stub_stays_inside_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scripts').mkdir();(root/'site/data').mkdir(parents=True)
            rel='data/timelines/xmr/example.json'
            write_json(root/rel,{'coverage':{'complete':False},'txs':[],'marker':'old'})
            class Runner:
                def run(self,gen,*args,**kwargs):
                    path=gen.root/rel
                    self_check=path.resolve().is_relative_to(gen.root)
                    if not self_check:raise AssertionError('Monero stub would escape staging')
                    write_json(path,{'coverage':{'complete':False},'txs':[],'marker':'new'})
                    if read_json(root/rel)['marker']!='old':raise AssertionError('Early publication')
                    return {'output':'{}','exit_code':0,'timed_out':False}
            with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'Generation',side_effect=lambda:Generation(root)):
                self.assertFalse(pipeline._refresh_source('utxo',Runner())['stale'])
            self.assertEqual(read_json(root/rel)['marker'],'new')

if __name__=='__main__':unittest.main()
