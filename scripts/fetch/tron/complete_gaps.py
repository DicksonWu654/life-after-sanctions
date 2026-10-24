"""Complete only the gaps between full-history prefixes and protected windows.

This avoids re-querying already complete designation/latest-90-day intervals.
Address locks ensure this repair never overlaps another writer.
"""
import argparse
import json
from collections import Counter
from common import Client,ROOT,load,save,timeline_path,utc,acquire_address_lock,set_bounds,missing
from fetch import run_stream,normalize_trc10,decode58

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--address',required=True)
    p.add_argument('--max-pages',type=int,default=4000)
    args=p.parse_args()
    decode58(args.address)
    c=Client()
    with acquire_address_lock('trx',args.address):
        path=timeline_path('trx',args.address);t=load(path)
        t['contract_types']=Counter(t.get('contract_types',{}))
        target=t.get('priority_snapshot_ms')
        if not target:raise SystemExit('Run windows.py first to establish the protected cutoff')
        repairs=t.setdefault('gap_repair',{})
        for name,parent in t['fetch_state'].items():
            known=list(parent['ranges'])
            known.extend(r for window in t.get('priority_windows',{}).values() for r in window.get(name,{}).get('ranges',[]))
            pending=missing([(r['from_ms'],r['to_ms']) for r in known],0,target)
            state=repairs.setdefault(name,{'pending':[{'lo':lo,'hi':hi} for lo,hi in pending],
                'ranges':[],'complete':not pending,'pages_fetched':0,'rows_fetched':0})
            if not missing([(r['from_ms'],r['to_ms']) for r in known+state['ranges']],0,target):
                state.update(pending=[],complete=not state.get('gaps'))
            run_stream(c,t,name,path,args.max_pages,state=state)
            known.extend(state['ranges'])
            known=list({(r['from_ms'],r['to_ms'],r.get('terminal_raw_ref')):r for r in known}.values())
            remaining=missing([(r['from_ms'],r['to_ms']) for r in known],0,target)
            if not remaining:
                parent.update(pending=[],ranges=known,complete=not parent.get('gaps'),
                              supplemental_pages=state['pages_fetched'])
            t['coverage'].setdefault('missing_time_windows',{})[name]=[{'from_ms':lo,'to_ms':hi} for lo,hi in remaining]
            save(path,t)
        t['coverage']['complete']=all(s['complete'] for s in t['fetch_state'].values()) and not t.get('unresolved_events')
        for name,field in (('native','native_transactions_complete'),('trc20','trc20_transfers_complete'),('internal','internal_transactions_complete')):
            t['coverage'][field]=t['fetch_state'][name]['complete']
        if t['coverage']['complete']:
            t['coverage']['checked_through_time']=utc(target)
            t['coverage']['notes']=[n for n in t['coverage']['notes'] if 'unfinished time windows remain' not in n]
            t['coverage']['notes'].append('Former gaps between full-history prefixes and protected windows were completed from saved gap_repair ranges.')
        normalize_trc10(t);set_bounds(t);save(path,t)
        print(json.dumps({'address':args.address,'events':len(t['txs']),'complete':t['coverage']['complete'],
                          'remaining':t['coverage']['missing_time_windows']}),flush=True)

if __name__=='__main__':main()
