"""Supplement protected TRC-20 windows using TronScan's public transfer API.

The public endpoint caps responses at 50 rows. Descending offset pages are
restarted at inclusive timestamp boundaries before the 10,000-row explorer cap.
All range proofs and normalized rows retain the original response references.
"""
import argparse
import json
from collections import Counter
from common import Client,FetchError,ROOT,acquire_address_lock,addresses,load,merge_txs,save,set_bounds,timeline_path
from fetch import SCAN,init_stream,parse_trc20
from windows import prepare_window


def scan_row(row):
    token=row['tokenInfo']
    return {'transaction_id':row['transaction_id'],'blockNumber':row.get('block'),
            'block_timestamp':row['block_ts'],'from':row['from_address'],'to':row['to_address'],
            'value':str(row['quant']),'type':row.get('event_type','Transfer'),
            'token_info':{'address':row['contract_address'],'decimals':int(token['tokenDecimal']),
                          'symbol':token.get('tokenAbbr')}}

def parse_scan_rows(rows,address,ref):
    events=[];occurrences=Counter()
    for i,row in enumerate(rows):
        if row.get('event_type','Transfer')!='Transfer' or row.get('revert') or row.get('finalResult','SUCCESS')!='SUCCESS':continue
        normalized=scan_row(row)
        if address not in (normalized['from'],normalized['to']):
            raise FetchError('TronScan address filter mismatch: '+ref)
        signature=json.dumps([normalized[k] for k in ('transaction_id','from','to','value','type')]+[normalized['token_info']['address']])
        event=parse_trc20(normalized,address,f'{ref}#/response/token_transfers/{i}',occurrences[signature])
        occurrences[signature]+=1
        event['indexer']='TronScan';events.append(event)
    return events


def run_scan(client,timeline,state,path,budget):
    events={e['event_id']:e for e in timeline['txs']}
    used=0
    def checkpoint():
        timeline['txs']=merge_txs(list(events.values()))
        set_bounds(timeline);save(path,timeline)
    while state['pending'] and used<budget:
        window=state['pending'][0]
        offset=window.get('scan_offset',0)
        params={'relatedAddress':timeline['address'],'sort':'-timestamp','limit':50,'start':offset,
                'start_timestamp':window['lo'],'end_timestamp':window['hi']}
        try:
            response,ref=client.get(SCAN+'/api/token_trc20/transfers',params,group='tronscan_trc20')
            rows=response.get('token_transfers') if isinstance(response,dict) else None
            if not isinstance(rows,list) or 'total' not in response:
                raise FetchError('Invalid TronScan transfer response: '+ref)
            total=int(response.get('rangeTotal',response['total']))
            times=[int(r['block_ts']) for r in rows]
            if times!=sorted(times,reverse=True) or any(ms<window['lo'] or ms>window['hi'] for ms in times):
                raise FetchError('TronScan did not honor descending timestamp bounds: '+ref)
            if len(rows)>50 or (not rows and total>offset):
                raise FetchError('Inconsistent TronScan row count: '+ref)
            if any(r.get('confirmed') is not True for r in rows):
                raise FetchError('Unconfirmed row inside a solid-head bounded range: '+ref)
            events.update((e['event_id'],e) for e in parse_scan_rows(rows,timeline['address'],ref))
        except (FetchError,KeyError,TypeError,ValueError) as error:
            state['error']=str(error);checkpoint();break
        used+=1
        state['pages_fetched']+=1;state['rows_fetched']+=len(rows);state['error']=None
        providers=state.setdefault('provider_pages',{})
        providers['TronScan']=providers.get('TronScan',0)+1
        offset+=len(rows)
        window['scan_offset']=offset
        window['scan_pages']=window.get('scan_pages',0)+1
        if len(rows)<50 or offset>=total:
            state['ranges'].append({'from_ms':window['lo'],'to_ms':window['hi'],
                'terminal_raw_ref':ref,'provider':'TronScan','order':'descending'})
            state['pending'].pop(0)
        elif window['scan_pages']>=5 and min(times)<window['hi']:
            boundary=min(times)
            state['ranges'].append({'from_ms':boundary+1,'to_ms':window['hi'],
                'terminal_raw_ref':ref,'provider':'TronScan','boundary_requeried_inclusively':True})
            state['pending'][0]={'lo':window['lo'],'hi':boundary}
        elif offset>=10000:
            boundary=min(times)
            state.setdefault('gaps',[]).append({'from_ms':boundary,'to_ms':boundary,
                'reason':'TronScan explorer cap reached within one millisecond','raw_ref':ref})
            state['pending'].pop(0)
            if window['lo']<boundary:state['pending'].insert(0,{'lo':window['lo'],'hi':boundary-1})
        state['complete']=not state['pending'] and not state.get('gaps')
        interval=5 if len(events)<100000 else 25
        if used%interval==0 or not state['pending']:checkpoint()
        if used%25==0:
            print(json.dumps({'address':timeline['address'],'provider':'TronScan','pages_this_pass':used,
                'pages_total':state['pages_fetched'],'events':len(events)}),flush=True)
    if used:checkpoint()
    return used


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addresses',default='data/addresses.csv')
    parser.add_argument('--address',action='append',required=True)
    parser.add_argument('--max-pages',type=int,default=4000)
    parser.add_argument('--delay',type=float,default=1.2)
    args=parser.parse_args();client=Client(delay=args.delay)
    for row in addresses(args.addresses):
        if row['chain']!='trx' or row['address'] not in args.address:continue
        with acquire_address_lock('trx',row['address']):
            path=timeline_path('trx',row['address']);timeline=load(path)
            requests=timeline.get('priority_window_requests',{})
            if not requests:raise SystemExit('Initialize protected windows with windows.py --max-pages 0 first')
            unions={}
            for request in requests.values():
                key=request['covered_by']
                old=unions.setdefault(key,[request['from_ms'],request['to_ms']])
                old[0]=min(old[0],request['from_ms']);old[1]=max(old[1],request['to_ms'])
            for key,(lo,hi) in unions.items():
                state=timeline['priority_windows'].setdefault(key,{}).setdefault('trc20',init_stream(lo,hi))
                prepare_window(timeline['fetch_state']['trc20'],timeline.get('gap_repair',{}).get('trc20',{}).get('ranges',[]),state,lo,hi)
                for window in state['pending']:window.pop('cursor',None)
                run_scan(client,timeline,state,path,args.max_pages)
            timeline['coverage']['priority_windows_complete']=all(s['complete'] for w in timeline['priority_windows'].values() for s in w.values())
            note='Protected TRC-20 ranges were supplemented with saved TronScan public 50-row descending pages; inclusive timestamp overlap avoids the explorer offset cap.'
            if note not in timeline['coverage']['notes']:timeline['coverage']['notes'].append(note)
            set_bounds(timeline);save(path,timeline)
            print(json.dumps({'address':row['address'],'protected_windows_complete':timeline['coverage']['priority_windows_complete'],
                              'network_calls':client.calls,'cache_hits':client.hits}),flush=True)


if __name__=='__main__':main()
