"""Scientific joins, cohort conservation and bounded display sampling."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.lib.site_enrichment import InflowIndex, compact_detail, enrich_headlines, sankey_cohorts


class ExportChecks(unittest.TestCase):
    def test_missing_flow_result_keeps_partial_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph=sankey_cohorts(Path(tmp),{'links':[]},{},{})
            self.assertEqual(graph['links'],[])
            self.assertIn('cohort_split_missing',graph)

    def test_class_join_uses_stable_identity_and_rejects_ambiguous_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'data/derived/inflows.csv';p.parent.mkdir(parents=True)
            base=dict.fromkeys(InflowIndex.FIELDS,'')
            base.update(chain='ETH',address='a',event_id='one',hash='hash',asset='USDT',amount='1.00',time_utc='2020-01-01T00:00:00Z',inflow_class='real',usd='1')
            with p.open('w') as f:
                w=csv.DictWriter(f,fieldnames=InflowIndex.FIELDS);w.writeheader();w.writerow(base)
            idx=InflowIndex(root)
            try:
                lookup=idx.address('eth','a')
                tx={'hash':'hash','asset':'USDT','amount':'1','time_utc':base['time_utc']}
                self.assertEqual(idx.match(lookup,tx,9)['inflow_class'],'real')
                lookup[1][('hash','USDT','1',base['time_utc'])].append(dict(base,event_id='two'))
                self.assertIsNone(idx.match(lookup,tx,9))
                self.assertEqual(idx.match(lookup,dict(tx,event_id='one'),9)['event_id'],'one')
            finally:idx.close()

    def test_cohort_split_allocates_each_program_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'data/derived/flows_edges.csv';path.parent.mkdir(parents=True)
            fields=['included_in_total','usd','is_dust','tornado_contract','self_transfer_same_address','source_entity_uids','destination_class','programs','chain']
            with path.open('w') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
                for uid,usd,programs in [('55505','90','A;B'),('2','10','A')]:
                    w.writerow(dict(zip(fields,['True',usd,'False','False','False',uid,'unlabelled',programs,'BTC'])))
            a={'source':'program:A','target':'class:unlabelled','value':55}
            b={'source':'program:B','target':'class:unlabelled','value':45}
            c={'source':'chain:BTC','target':'class:unlabelled','value':100}
            result={'summary':{'wallet_outflows_usd':{'value':100}},'sankey':{'program':{'links':[a,b]},'chain':{'links':[c]}}}
            graph=sankey_cohorts(root,{}, {'55505':{'CHEN, Zhi'},'2':{'OFAC NAME'}},result)
            remaining=graph['links_excluding']['CHEN, Zhi']
            self.assertEqual({(r['source'],r['value']) for r in remaining},{('program:A',10),('chain:BTC',10)})
            for link in graph['links']:self.assertEqual(sum(c['value'] for c in link['by_cohort']),link['value'])

    def test_byte_bound_preserves_issuer_events_and_monthly_totals(self):
        d={'id':'btc:a','events':[{'time':f'2020-01-{1+i%28:02}T00:00:00Z','kind':'in','usd':i,'tx':str(i),'asset':'BTC','amount':1} for i in range(3000)],
           'monthly_counts':[{'month':'2020-01','in':3000,'out':0}],
           'truncation':{'observed_transfer_events':3000,'designation_window_dates':['2020-01-01'],'observed_designation_window_transfers':800}}
        d['events'].append({'time':'2010-01-01T00:00:00Z','kind':'freeze','tx':'freeze'})
        compact_detail(d,cap=2000,byte_limit=50_000)
        self.assertLessEqual(len(json.dumps(d,separators=(',',':')).encode())+1,50_000)
        self.assertTrue(any(e['kind']=='freeze' for e in d['events']))
        self.assertEqual(d['monthly_counts'][0]['in'],3000)
        self.assertGreater(d['truncation']['omitted_transfer_events'],0)

if __name__=='__main__':unittest.main()
