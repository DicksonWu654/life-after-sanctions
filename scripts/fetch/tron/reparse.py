"""Rebuild normalized events from cached responses without network requests.

This is also an independent reproducibility check: all timeline transfer amounts
are derived again from evidence rather than trusting the existing aggregates.
"""
import argparse
import urllib.parse
from collections import Counter
from contextlib import ExitStack
from common import ROOT,addresses,load,merge_txs,save,set_bounds,timeline_path,acquire_address_lock
from fetch import parse_native,parse_trc20,parse_internal,normalize_trc10,token_resolution_key
from fallback_tokens import parse_scan_rows

def rebuild(chosen):
    rows={};types={};responses=0;native_ids={};internal_ids={};resolutions={};native_blocks={};fee_resolutions={}
    for group in ('native','trc20','internal','tronscan_trc20'):
        for path in sorted((ROOT/'data/raw/tron'/group).glob('*.json.gz')):
            obj=load(path)
            payload=obj.get('response')
            if not isinstance(payload,dict):continue
            if group=='tronscan_trc20':
                if not isinstance(payload.get('token_transfers'),list):continue
            elif payload.get('success') is not True or not isinstance(payload.get('data'),list):continue
            url=obj['request']['url']
            try:addr=(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['relatedAddress'][0] if group=='tronscan_trc20' else url.split('/v1/accounts/')[1].split('/')[0])
            except IndexError:continue
            if addr not in chosen:continue
            rows.setdefault(addr,[]);types.setdefault(addr,Counter())
            native_ids.setdefault(addr,set());internal_ids.setdefault(addr,set())
            native_blocks.setdefault(addr,{})
            ref=str(path.relative_to(ROOT));occ=Counter()
            if group=='tronscan_trc20':
                rows[addr].extend(parse_scan_rows(obj['response']['token_transfers'],addr,ref))
                responses+=1;continue
            for i,row in enumerate(obj['response'].get('data',[])):
                raw=f'{ref}#/response/data/{i}'
                if group=='native':
                    if row['txID'] in native_ids[addr]:continue
                    native_ids[addr].add(row['txID'])
                    if row.get('blockNumber') is not None:native_blocks[addr][row['txID']]=(row['blockNumber'],raw)
                    if addr not in fee_resolutions:
                        tp=timeline_path('trx',addr)
                        fee_resolutions[addr]=load(tp).get('fee_resolution',{}) if tp.exists() else {}
                    events,kinds=parse_native(row,addr,raw,fee_resolutions[addr].get(row['txID']))
                    rows[addr].extend(events);types[addr].update(kinds)
                elif group=='internal':
                    if row['internal_tx_id'] in internal_ids[addr]:continue
                    internal_ids[addr].add(row['internal_tx_id'])
                    rows[addr].extend(parse_internal(row,addr,raw))
                elif row.get('type','Transfer')=='Transfer':
                    import json
                    sig=json.dumps(row,sort_keys=True)
                    resolution=None
                    if not (row.get('token_info') or {}).get('address'):
                        if addr not in resolutions:
                            tp=timeline_path('trx',addr)
                            resolutions[addr]=load(tp).get('token_resolution',{}) if tp.exists() else {}
                        resolution=resolutions[addr].get(token_resolution_key(row))
                    rows[addr].append(parse_trc20(row,addr,raw,occ[sig],resolution));occ[sig]+=1
            responses+=1
    events=0
    for addr,txs in rows.items():
        path=timeline_path('trx',addr)
        if not path.exists():continue
        t=load(path);t['txs']=merge_txs(txs);t['contract_types']=types[addr]
        t['coverage']['notes']=[('TronGrid TRC-20 responses omit block numbers/log indexes; available native, receipt or TronScan evidence supplies blocks, otherwise they remain null.'
            if note.startswith('TronGrid TRC-20 responses omit block numbers') else note) for note in t['coverage']['notes']]
        for e in t['txs']:
            if e.get('block') is None and e['hash'] in native_blocks[addr]:
                e['block'],e['block_raw_ref']=native_blocks[addr][e['hash']]
        t['source_unique_counts']={'native_transactions':len(native_ids[addr]),'internal_calls':len(internal_ids[addr]),
             'normalized_events':len(t['txs'])}
        for b in t['balance_now']:
            if isinstance(b.get('raw_ref'),str):
                rawpath=b['raw_ref'].partition('#')[0]
                if b['asset']=='TRX' and b['source'].endswith('/wallet/getaccount'):
                    b['raw_ref']=rawpath+'#/response'
                if (ROOT/rawpath).exists():b['as_of']=load(ROOT/rawpath)['requested_at']
        normalize_trc10(t);set_bounds(t);save(path,t);events+=len(t['txs'])
    print({'addresses':len(rows),'raw_responses_reparsed':responses,'events':events})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/bootstrap/fetch_tron.csv')
    args=p.parse_args()
    chosen={r['address'] for r in addresses(args.addresses) if r['chain']=='trx'}
    # Acquire the full write scope before touching a timeline. A missed active
    # fetch must abort the reparse rather than silently replace its checkpoint.
    with ExitStack() as locks:
        for addr in sorted(chosen):locks.enter_context(acquire_address_lock('trx',addr))
        rebuild(chosen)

if __name__=='__main__':main()
