"""Regression checks for observed API schemas, fees and capped timestamp paging."""
import tempfile
import time
import unittest
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pathlib import Path
from common import Client,blank,amount,save,load,acquire_address_lock,BusyAddress
from fetch import fetch_one,prepare_incremental,merge_incremental,parse_internal,parse_native,parse_trc20,run_stream,init_stream,encode58
from windows import prepare_window
from validate import check_protected_windows
from fallback_tokens import parse_scan_rows,run_scan

A=encode58('41'+'11'*20)
B=encode58('41'+'22'*20)

class FetchTests(unittest.TestCase):
    def test_interrupted_refresh_keeps_unfetched_tail_when_next_head_is_behind(self):
        t=blank('trx',A,'fixture')
        parent=dict(init_stream(0,1000),pending=[{'lo':101,'hi':1000}],ranges=[{'from_ms':0,'to_ms':100}])
        t['fetch_state']={'native':parent}
        t['incremental_refresh']={'native':dict(init_stream(100,2000),
            pending=[{'lo':1501,'hi':2000}],ranges=[{'from_ms':100,'to_ms':1500}],pages_fetched=2)}
        prepare_incremental(t,1900,0)
        fresh=t['incremental_refresh']['native']
        fresh.update(pending=[],ranges=[{'from_ms':1500,'to_ms':1900}],complete=True,pages_fetched=1)
        merge_incremental(t,1900)
        self.assertEqual(parent['pending'],[{'lo':1901,'hi':2000}])
        self.assertEqual(parent['pages_fetched'],3)
        self.assertFalse(parent['complete'])

    def test_partial_refresh_queries_only_after_the_latest_protected_boundary(self):
        class Fake:
            def __init__(self):self.requests=[]
            def get(self,url,params,**kw):
                self.requests.append(dict(params))
                return {'success':True,'data':[],'meta':{}},'new-range'
        t=blank('trx',A,'fixture');t['coverage']['history_head_finality']='solid'
        t['fetch_state']={name:dict(init_stream(0,1000),pending=[],ranges=[{'from_ms':0,'to_ms':1000}],complete=True)
                          for name in ('native','trc20','internal')}
        t['fetch_state']['native'].update(pending=[{'lo':101,'hi':1000}],ranges=[{'from_ms':0,'to_ms':100}],complete=False)
        t['priority_windows']={'protected':{'native':{'ranges':[{'from_ms':500,'to_ms':1000}]}}}
        args=SimpleNamespace(refresh=True,history_only=True,max_pages=10,no_labels=False)
        client=Fake()
        with tempfile.TemporaryDirectory() as directory,patch('common.ROOT',Path(directory)):
            path=Path(directory)/'data/timelines/trx'/(A+'.json.gz');save(path,t)
            for boundary,new_head in ((1000,2000),(2000,3000)):
                result=fetch_one(client,{'address':A},args,{'timestamp':new_head,'number':2,'raw_ref':'head','_observed':time.monotonic()})
                self.assertTrue(all(r['min_timestamp']==boundary for r in client.requests[-3:]))
                self.assertEqual(result['fetch_state']['native']['pending'],[{'lo':101,'hi':499}])
                self.assertFalse(result['coverage']['complete'])

    def test_refresh_can_finish_an_interrupted_prefix_and_default_rerun_skips_history(self):
        class Fake:
            def __init__(self):self.requests=[]
            def get(self,url,params,**kw):
                self.requests.append(dict(params))
                return {'success':True,'data':[],'meta':{}},'new-range'
        t=blank('trx',A,'fixture');t['coverage']['history_head_finality']='solid'
        t['fetch_state']={name:dict(init_stream(0,1000),pending=[],ranges=[{'from_ms':0,'to_ms':1000}],complete=True)
                          for name in ('native','trc20','internal')}
        t['fetch_state']['native'].update(pending=[{'lo':101,'hi':1000}],ranges=[{'from_ms':0,'to_ms':100}],complete=False)
        args=SimpleNamespace(refresh=True,history_only=True,max_pages=10,no_labels=False);client=Fake()
        with tempfile.TemporaryDirectory() as directory,patch('common.ROOT',Path(directory)):
            save(Path(directory)/'data/timelines/trx'/(A+'.json.gz'),t)
            head={'timestamp':2000,'number':2,'raw_ref':'head','_observed':time.monotonic()}
            result=fetch_one(client,{'address':A},args,head)
            self.assertEqual(client.requests[0]['min_timestamp'],100)
            self.assertTrue(result['coverage']['complete'])
            before=len(client.requests);args.refresh=False
            fetch_one(client,{'address':A},args,head)
            self.assertEqual(len(client.requests),before)

    def test_tronscan_and_trongrid_normalize_to_the_same_event_id(self):
        row={'transaction_id':'h','block':7,'block_ts':1700000000000,'from_address':B,'to_address':A,
             'quant':'1234567','event_type':'Transfer','confirmed':True,'contract_address':'token',
             'tokenInfo':{'tokenDecimal':6,'tokenAbbr':'T'}}
        scan=parse_scan_rows([row],A,'scan')[0]
        grid=parse_trc20({'transaction_id':'h','block_timestamp':1700000000000,'from':B,'to':A,
             'value':'1234567','type':'Transfer','token_info':{'address':'token','decimals':6,'symbol':'T'}},A,'grid')
        self.assertEqual(scan['event_id'],grid['event_id'])
        self.assertEqual(scan['amount'],'1.234567')
        self.assertEqual(scan['block'],7)

    def test_tronscan_descending_window_boundary_is_requeried_inclusively(self):
        class Fake:
            calls=0
            def get(self,url,params,**kw):
                self.calls+=1
                if params['end_timestamp']!=1000:
                    self.boundary=params['end_timestamp']
                    return {'total':0,'rangeTotal':0,'token_transfers':[]},'scan-final'
                start=params['start']
                data=[{'transaction_id':str(i),'block_ts':1000-i,'from_address':B,'to_address':A,
                    'quant':'1','event_type':'Transfer','confirmed':True,'contract_address':'token',
                    'tokenInfo':{'tokenDecimal':6,'tokenAbbr':'T'}} for i in range(start,start+50)]
                return {'total':10000,'rangeTotal':20000,'token_transfers':data},'scan'
        client=Fake();timeline=blank('trx',A,'scan');state=init_stream(0,1000)
        with tempfile.TemporaryDirectory() as directory:
            run_scan(client,timeline,state,Path(directory)/'timeline.json.gz',20)
        self.assertEqual(client.boundary,751)
        self.assertTrue(state['complete'])
        self.assertEqual(len(timeline['txs']),250)

    def test_provider_backoff_is_shared_by_independent_clients(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('common.ROOT',Path(directory)),patch('common.time.time',return_value=100),patch('common.time.sleep') as sleep:
                Client().shared_backoff('api.trongrid.io',12)
                Client().rate_gate('api.trongrid.io')
                sleep.assert_called_once_with(12)

    def test_protected_window_includes_a_previously_complete_stream_tail(self):
        parent={'ranges':[{'from_ms':0,'to_ms':99}],'complete':True}
        state=prepare_window(parent,[],init_stream(50,120),50,120)
        self.assertEqual(state['pending'],[{'lo':100,'hi':120}])
        self.assertFalse(state['complete'])
        state.update(pending=[],ranges=[{'from_ms':100,'to_ms':120}],complete=True)
        # An additional official date can expand a previously completed union.
        prepare_window(parent,[],state,50,150)
        self.assertEqual(state['pending'],[{'lo':121,'hi':150}])
        state['pending'][0]['cursor']='resumable'
        prepare_window(parent,[],state,50,150)
        self.assertEqual(state['pending'][0]['cursor'],'resumable')

    def test_protected_window_validation_checks_ranges_instead_of_flags(self):
        t={'chain':'trx','coverage':{'priority_window_dates_available':True,'priority_windows_complete':True},
           'fetch_state':{'native':{'complete':False,'ranges':[{'from_ms':0,'to_ms':99}]}},
           'priority_window_requests':{'designation':{'from_ms':50,'to_ms':120}},
           'priority_windows':{'union':{'native':{'ranges':[{'from_ms':101,'to_ms':120}]}}}}
        errors=check_protected_windows(t)
        self.assertEqual(errors[0]['missing_intervals_ms'],[(100,100)])
        t['gap_repair']={'native':{'ranges':[{'from_ms':100,'to_ms':100}]}}
        self.assertEqual(check_protected_windows(t),[])

    def test_internal_current_schema(self):
        row={'tx_id':'parent','internal_tx_id':'internal','block_timestamp':1700000000000,
             'from_address':'41'+'22'*20,'to_address':'41'+'11'*20,
             'data':{'note':'call','rejected':False,'call_value':{'_':68003718}}}
        result=parse_internal(row,A,'fixture#/0')
        self.assertEqual([(r['direction'],r['amount']) for r in result],[('in','68.003718')])
        row['data']['rejected']=True
        self.assertEqual(parse_internal(row,A,'fixture#/0'),[])

    def test_incoming_fee_belongs_to_sender_and_failed_value_is_excluded(self):
        tx={'txID':'payment','block_timestamp':1700000000000,'blockNumber':7,
            'ret':[{'contractRet':'SUCCESS','fee':1100000}],
            'raw_data':{'contract':[{'type':'TransferContract','parameter':{'value':{
                'owner_address':'41'+'22'*20,'to_address':'41'+'11'*20,'amount':7000000}}}]}}
        incoming,_=parse_native(tx,A,'fixture#/0')
        self.assertEqual([(r['amount'],r['fee']) for r in incoming],[('7','0')])
        tx['ret'][0]['contractRet']='OUT_OF_ENERGY'
        sender,_=parse_native(tx,B,'fixture#/0')
        self.assertEqual([(r['amount'],r['fee']) for r in sender],[('0','1.1')])
        tx['ret'][0]['fee']=0
        sender,_=parse_native(tx,B,'fixture#/0',{'fee_sun':1100000,'raw_ref':'receipt#/response/fee'})
        self.assertEqual(sender[0]['fee'],'1.1')
        self.assertEqual(sender[0]['fee_raw_ref'],'receipt#/response/fee')

    def test_cap_boundary_is_inclusive_and_completed_rerun_is_offline(self):
        class Fake:
            calls=0
            def get(self,url,params,**kw):
                self.calls+=1
                page=int(params.get('fingerprint','0'))
                # Five full provider pages, followed by a fresh time window.
                if params['min_timestamp']==0:
                    start=page*200
                    data=[{'transaction_id':str(i),'token_info':{'address':'token','symbol':'T','decimals':6},
                           'block_timestamp':1700000000000+i,'from':B,'to':A,'value':'1','type':'Transfer'}
                          for i in range(start,start+200)]
                    return {'success':True,'data':data,'meta':{'fingerprint':str(page+1)}},'fixture'
                self.assert_boundary=params['min_timestamp']
                return {'success':True,'data':[],'meta':{}},'fixture-final'
        c=Fake();t=blank('trx',A,'fixture');t['contract_types']={}
        t['fetch_state']={'trc20':init_stream(0,1800000000000)}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'timeline.json.gz'
            run_stream(c,t,'trc20',path,20)
            self.assertEqual(c.assert_boundary,1700000000999)
            self.assertTrue(t['fetch_state']['trc20']['complete'])
            self.assertEqual(len(t['txs']),1000)
            before=c.calls
            run_stream(c,t,'trc20',path,20)
            self.assertEqual(c.calls,before)

    def test_missing_token_metadata_uses_receipt_resolution(self):
        row={'transaction_id':'h','token_info':{},'block_timestamp':1700000000000,
             'from':B,'to':A,'value':'0','type':'Transfer'}
        resolved={'address':'contract','decimals':6,'symbol':None,'blockNumber':7,
                  'asset_raw_ref':'receipt#/response/log/0'}
        event=parse_trc20(row,A,'indexer#/response/data/0',resolution=resolved)
        self.assertEqual((event['asset'],event['block'],event['amount']),('contract',7,'0'))
        self.assertEqual(event['asset_raw_ref'],'receipt#/response/log/0')
        row['token_info']={'symbol':'missing-contract'}
        self.assertEqual(parse_trc20(row,A,'indexer',resolution=resolved)['asset'],'contract')

    def test_large_token_integer_is_not_rounded_to_decimal_default_precision(self):
        value=str(2**256-1)
        rendered=amount(value,18)
        self.assertEqual(rendered.replace('.','').lstrip('0'),value)

    def test_address_writer_lock_and_atomic_snapshot_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('common.ROOT',root):
                with acquire_address_lock('trx','fixture'):
                    with self.assertRaises(BusyAddress):acquire_address_lock('trx','fixture')
                with acquire_address_lock('trx','fixture'):pass
            path=root/'shared.json.gz'
            def write(i):save(path,{'writer':i,'payload':['value']*2000})
            with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(write,range(20)))
            self.assertIn(load(path)['writer'],range(20))
            self.assertEqual(list(root.glob('*.tmp')),[])

if __name__=='__main__':unittest.main()
