"""Fetch designation T-60..T+400 and latest-90-day windows for unfinished wallets.

Official dates must come from data/ledger.csv (not inferred from first activity).
This script never substitutes a priority window for a full-history completeness
claim. Exact residual full-history windows remain in the parent fetch_state.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime,timezone
from common import Client,ROOT,addresses,load,save,now,timeline_path,acquire_address_lock
from fetch import API,HEAD_API,init_stream,run_stream,normalize_trc10
from complete_gaps import missing as missing_intervals

DAY=86400000

def prepare_window(parent,supplemental,state,lo,hi):
    """Reuse proven coverage while retaining a resumable cursor when possible."""
    known=list(parent['ranges'])+list(supplemental)+list(state.get('ranges',[]))
    pending=missing_intervals([(r['from_ms'],r['to_ms']) for r in known],lo,hi)
    old=state.get('pending',[])
    bounded=all(lo<=w['lo']<=w['hi']<=hi for w in old)
    same=(bounded and missing_intervals([(w['lo'],w['hi']) for w in old],lo,hi)
          ==missing_intervals(pending,lo,hi))
    if not same:state['pending']=[{'lo':a,'hi':b} for a,b in pending]
    state['complete']=not state['pending'] and not state.get('gaps')
    state['requested_bounds']={'from_ms':lo,'to_ms':hi}
    return state

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/bootstrap/fetch_tron.csv')
    p.add_argument('--ledger',default='data/ledger.csv')
    p.add_argument('--max-pages',type=int,default=1000)
    p.add_argument('--delay',type=float,default=1.1)
    p.add_argument('--address',action='append',help='Limit priority repair to explicitly selected inactive fetch writers')
    p.add_argument('--head-ref',help='Reuse a saved solid-head response instead of making a new head request')
    args=p.parse_args()
    c=Client(delay=args.delay)
    dates={};date_sources={}
    ledger=ROOT/args.ledger
    if ledger.exists():
        for row in csv.DictReader(ledger.open()):
            a=row.get('address_normalized') or row.get('address')
            values=[{'date':row.get('listed_date') or row.get('first_listed_date'),
                     'raw_ref':row.get('listed_raw_ref'),'url':row.get('listed_action_url')}]
            try:values.extend(json.loads(row.get('listing_events') or '[]'))
            except (ValueError,TypeError):pass
            for event in values:
                value=event.get('date')
                if not value or event.get('kind') in ('delisting','removal'):continue
                try:ms=int(datetime.fromisoformat(value.replace('Z','+00:00')).replace(tzinfo=timezone.utc).timestamp()*1000)
                except ValueError:continue
                dates.setdefault(a,set()).add((value,ms))
                date_sources.setdefault(a,{})[value]={'date':value,'raw_ref':event.get('raw_ref'),
                    'source_url':event.get('url'),'ledger_path':str(ledger.relative_to(ROOT))}
    if args.head_ref:
        ref=args.head_ref;raw=load(ROOT/ref)
        if raw['request']['url']!=HEAD_API:raise SystemExit('head-ref must be a saved solidity-head response')
        obj=raw['response']
    else:obj,ref=c.request(HEAD_API,{},group='head',fresh=True)
    head_hi=obj['block_header']['raw_data']['timestamp']
    for row in addresses(args.addresses):
        if row['chain']!='trx':continue
        if args.address and row['address'] not in args.address:continue
        path=timeline_path('trx',row['address'])
        if not path.exists():continue
        lock=acquire_address_lock('trx',row['address'])
        t=load(path)
        t['contract_types']=Counter(t.get('contract_types',{}))
        unfinished=[name for name,s in t.get('fetch_state',{}).items() if not s['complete']]
        if not unfinished:
            lock.close();continue
        hi=t.setdefault('priority_snapshot_ms',head_hi)
        windows=[('latest_90_days',max(0,hi-90*DAY),hi)]
        windows.extend(('designation_'+d,max(0,ms-60*DAY),min(hi,ms+400*DAY)) for d,ms in dates.get(row['address'],set()))
        state=t.setdefault('priority_windows',{})
        t['priority_window_designations']=date_sources.get(row['address'],{})
        # Query overlapping date windows once. Each original requirement maps
        # to a union with the same provable coverage, avoiding duplicate calls.
        unions=[]
        for key,lo,end in sorted(windows,key=lambda w:w[1]):
            if unions and lo<=unions[-1]['hi']+1:
                unions[-1]['hi']=max(unions[-1]['hi'],end);unions[-1]['members'].append(key)
            else:unions.append({'lo':lo,'hi':end,'members':[key]})
        t['priority_window_requests']={key:{'from_ms':lo,'to_ms':end} for key,lo,end in windows}
        for i,union in enumerate(unions):
            key='protected_union_'+str(i);lo,end=union['lo'],union['hi']
            for member in union['members']:t['priority_window_requests'][member]['covered_by']=key
            for name,parent in t['fetch_state'].items():
                # A previously finished stream may end before this protected
                # snapshot. Reuse its proven ranges and query only the tail.
                s=state.setdefault(key,{}).setdefault(name,init_stream(lo,end))
                prepare_window(parent,t.get('gap_repair',{}).get(name,{}).get('ranges',[]),s,lo,end)
                run_stream(c,t,name,path,args.max_pages,state=s)
        t['coverage']['priority_window_dates_available']=bool(dates.get(row['address']))
        t['coverage']['priority_windows_complete']=all(s['complete'] for w in state.values() for s in w.values())
        t['coverage']['priority_window_head_raw_ref']=ref
        missing={}
        for name,parent in t['fetch_state'].items():
            known=list(parent['ranges'])
            known.extend(r for window in state.values() for r in window.get(name,{}).get('ranges',[]))
            known.extend(t.get('gap_repair',{}).get(name,{}).get('ranges',[]))
            intervals=missing_intervals([(r['from_ms'],r['to_ms']) for r in known],0,hi)
            missing[name]=[{'from_ms':lo,'to_ms':end} for lo,end in intervals]
        t['coverage']['missing_time_windows']=missing
        normalize_trc10(t);save(path,t)
        print(json.dumps({'address':row['address'],'priority_windows':len(windows),
                         'complete':t['coverage']['priority_windows_complete'],'designation_dates_available':bool(dates.get(row['address']))}),flush=True)
        lock.close()
    save(ROOT/'data/raw/tron/priority-run-summary.json.gz',{'fetched_at':now(),'ledger_available':ledger.exists(),
         'addresses_with_dates':len(dates),'http_errors':c.errors,'network_calls':c.calls})

if __name__=='__main__':main()
