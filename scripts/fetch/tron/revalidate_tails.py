"""Recheck legacy latest-head cutoff tails against a proven solid chain head.

Older collection versions used latest block with only_confirmed=true. Requery
the last two minutes once after those blocks are solid, then use solidity heads
for subsequent incremental refreshes. No latest balance is substituted here.
"""
import argparse
import json
import urllib.parse
from datetime import datetime
from collections import Counter
from common import Client,ROOT,addresses,load,save,timeline_path,acquire_address_lock,BusyAddress,now
from fetch import HEAD_API,init_stream,run_stream,normalize_trc10

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/addresses.csv')
    p.add_argument('--max-pages',type=int,default=100)
    p.add_argument('--include-partial',action='store_true',help='Also confirm original stream cutoffs inside merged protected histories')
    args=p.parse_args();c=Client();reports=[]
    obj,headref=c.request(HEAD_API,{},group='head',fresh=True)
    solid=obj['block_header']['raw_data']['timestamp']
    for row in addresses(args.addresses):
        if row['chain']!='trx':continue
        path=timeline_path('trx',row['address'])
        if not path.exists():continue
        try:lock=acquire_address_lock('trx',row['address'])
        except BusyAddress:continue
        with lock:
            t=load(path);parents=t.get('fetch_state',{})
            if not parents or (not args.include_partial and not all(s['complete'] for s in parents.values())):continue
            if t['coverage'].get('history_head_finality') in ('solid','solid_revalidated'):continue
            ends={name:max(r['to_ms'] for r in s['ranges']) for name,s in parents.items() if s['ranges']}
            if not ends:continue
            if max(ends.values())>solid:continue
            t['contract_types']=Counter(t.get('contract_types',{}))
            states=t.setdefault('tail_revalidation',{})
            for name,end in ends.items():
                s=states.setdefault(name,init_stream(max(0,end-120000),end))
                run_stream(c,t,name,path,args.max_pages,state=s)
            if args.include_partial:
                for name,parent in parents.items():
                    for interval in parent['ranges']:
                        # A range exhausted near a latest-head query can be
                        # embedded inside a later merged history. Preserve and
                        # confirm its original boundary as well as the new end.
                        if interval.get('boundary_requeried_inclusively'):continue
                        ref=interval.get('terminal_raw_ref')
                        if not ref:continue
                        raw=load(ROOT/ref)
                        query=urllib.parse.parse_qs(urllib.parse.urlsplit(raw['request']['url']).query)
                        bound=int(query.get('max_timestamp',['-1'])[0])
                        requested=int(datetime.fromisoformat(raw['requested_at'].replace('Z','+00:00')).timestamp()*1000)
                        if bound!=interval['to_ms'] or not -5000<=requested-bound<=120000 or bound>solid:continue
                        key=name+':legacy:'+str(bound)
                        s=states.setdefault(key,init_stream(max(0,bound-120000),bound))
                        run_stream(c,t,name,path,args.max_pages,state=s)
            done=all(s['complete'] for s in states.values())
            if done:
                t['coverage']['history_head_finality']='solid_revalidated'
                t['coverage']['tail_confirmation_head_raw_ref']=headref
                t['coverage']['tail_revalidated_at']=now()
            normalize_trc10(t);save(path,t)
            report={'address':row['address'],'complete':done,'events':len(t['txs']),
                    'timeline_ref':str(path.relative_to(ROOT))}
            reports.append(report);print(json.dumps(report),flush=True)
    save(ROOT/'data/raw/tron/tail-revalidation-summary.json.gz',{'checked_at':now(),'reports':reports,
         'confirmation_head_raw_ref':headref,'network_calls':c.calls,'http_errors':c.errors})

if __name__=='__main__':main()
