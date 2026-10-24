"""Offline contract, provenance-pointer and exact balance reconciliation checks."""
from __future__ import annotations
import argparse
import json
import hashlib
from collections import Counter,defaultdict
from decimal import Decimal,localcontext
from pathlib import Path
from common import ROOT,addresses,load,now,save,timeline_path
from complete_gaps import missing as missing_intervals

def check_protected_windows(t):
    """Verify coverage by interval union, independently of completion flags."""
    if t['chain']!='trx':return []
    parents=t.get('fetch_state',{})
    if parents and all(s.get('complete') for s in parents.values()):return []
    errors=[]
    requests=t.get('priority_window_requests',{})
    if not requests:return ['Unfinished Tron history has no protected designation/recent windows']
    if not t['coverage'].get('priority_window_dates_available'):
        errors.append('Official designation dates unavailable for unfinished history')
    for label,request in requests.items():
        for name,parent in parents.items():
            ranges=list(parent.get('ranges',[]))
            ranges.extend(r for window in t.get('priority_windows',{}).values() for r in window.get(name,{}).get('ranges',[]))
            ranges.extend(t.get('gap_repair',{}).get(name,{}).get('ranges',[]))
            pending=missing_intervals([(r['from_ms'],r['to_ms']) for r in ranges],request['from_ms'],request['to_ms'])
            if pending:errors.append({'window':label,'stream':name,'missing_intervals_ms':pending})
    return errors

def resolve(ref,cache):
    path,_,pointer=ref.partition('#')
    if path in cache:obj=cache.pop(path)
    else:obj=load(ROOT/path)
    cache[path]=obj
    # Large wallets reference thousands of full 200-row responses. Keep a
    # bounded LRU instead of retaining gigabytes of decoded API documents.
    if len(cache)>32:cache.pop(next(iter(cache)))
    for part in pointer.strip('/').split('/') if pointer else []:
        part=part.replace('~1','/').replace('~0','~')
        obj=obj[int(part)] if isinstance(obj,list) else obj[part]
    return obj

def check(t,cache):
    errors=[];ids=set()
    for field in ('chain','address','fetched_at','source','coverage','txs','balance_now'):
        if field not in t:errors.append('Missing field '+field)
    if not isinstance(t['coverage']['complete'],bool):errors.append('complete is not boolean')
    if t['chain']=='trx':
        if t.get('fetch_state') and t['coverage'].get('history_head_finality') not in ('solid','solid_revalidated'):
            errors.append('History cutoff confirmation audit is pending')
        if any(not state.get('complete') for state in t.get('tail_revalidation',{}).values()):
            errors.append('Confirmation-tail paging is unfinished')
        present={b['asset'] for b in t['balance_now']}
        for asset in ('TRX','TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'):
            if asset not in present:errors.append('Missing mandatory current API balance: '+asset)
        for name,field in (('native','native_transactions_complete'),('trc20','trc20_transfers_complete'),('internal','internal_transactions_complete')):
            if field in t['coverage'] and t['coverage'][field]!=t.get('fetch_state',{}).get(name,{}).get('complete'):
                errors.append('Stream completion flag disagrees with fetch_state: '+name)
    for i,tx in enumerate(t['txs']):
        for f in ('hash','block','time_utc','direction','asset','symbol','decimals','amount','counterparties','fee','raw_ref'):
            if f not in tx:errors.append(f'txs[{i}] missing {f}')
        if tx.get('direction') not in ('in','out','self'):errors.append(f'txs[{i}] invalid direction')
        if not isinstance(tx.get('amount'),str):errors.append(f'txs[{i}] amount is not decimal string')
        if Decimal(tx['amount'])<0:errors.append(f'txs[{i}] negative amount')
        if Decimal(tx['fee'])<0:errors.append(f'txs[{i}] negative fee')
        if tx.get('event_id') in ids:errors.append(f'txs[{i}] duplicate event_id')
        ids.add(tx.get('event_id'))
        try:resolve(tx['raw_ref'],cache)
        except (OSError,KeyError,IndexError,ValueError,TypeError) as e:errors.append(f'txs[{i}] bad raw_ref: {e}')
        extras=list(tx.get('owner_resolution_raw_refs',[]))
        if tx.get('metadata_raw_ref'):extras.append(tx['metadata_raw_ref'])
        if tx.get('block_raw_ref'):extras.append(tx['block_raw_ref'])
        if tx.get('asset_raw_ref'):extras.append(tx['asset_raw_ref'])
        if tx.get('fee_raw_ref'):extras.append(tx['fee_raw_ref'])
        for ref in extras:
            try:resolve(ref,cache)
            except (OSError,KeyError,IndexError,ValueError,TypeError) as e:errors.append(f'txs[{i}] bad metadata raw_ref: {e}')
    for b in t['balance_now']:
        for ref in b['raw_ref'] if isinstance(b['raw_ref'],list) else [b['raw_ref']]:
            try:resolve(ref,cache)
            except (OSError,KeyError,IndexError,ValueError,TypeError) as e:errors.append(f'balance {b["asset"]} bad raw_ref: {e}')
    return errors

def reconcile(t):
    net=defaultdict(Decimal);fees=defaultdict(Decimal)
    for tx in t['txs']:
        v=Decimal(tx['amount'])
        if tx['direction']=='in':net[tx['asset']]+=v
        elif tx['direction']=='out':net[tx['asset']]-=v
        # Fees in each native-asset row only. No fee is charged to a token.
        fees[tx['asset']]+=Decimal(tx['fee'])
    rows=[]
    for b in t['balance_now']:
        asset=b['asset'];observed=Decimal(b['amount']);computed=net[asset]-fees[asset]
        delta=computed-observed
        decimals=b.get('decimals')
        dust=Decimal(10)**-int(decimals) if decimals is not None else Decimal('1e-12')
        matched=abs(delta)<=dust
        reason='Exact/dust match' if matched else 'Unexplained balance discrepancy; do not treat complete paging as reconciliation'
        state=t.get('fetch_state',{})
        pending=any(s.get('pending') for s in state.values() if isinstance(s,dict))
        if t['chain']=='trx':
            streams=('native','internal') if asset=='TRX' or asset.startswith('trc10:') else ('trc20',)
            pending=any(state.get(name,{}).get('pending') or state.get(name,{}).get('gaps') for name in streams)
        if not matched and pending:reason='Unfinished history windows; see coverage.missing_time_windows and saved range proofs'
        elif not matched and t['chain']=='trx':
            if asset=='TRX' and any(k in t.get('contract_types',{}) for k in ('FreezeBalanceContract','UnfreezeBalanceContract','FreezeBalanceV2Contract','UnfreezeBalanceV2Contract','WithdrawBalanceContract','WithdrawExpireUnfreezeContract','DelegateResourceContract')):
                reason='Staking/resource/reward operations are present; their liquid-balance effects are not normalized, and unaudited indexer fees may also differ'
            elif asset=='TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':
                reason='USDT Transfer sum differs from direct balanceOf; issuer burns without Transfer, indexing omissions or snapshot drift require separate evidence (cause unconfirmed)'
            elif asset.startswith('trc10:'):
                reason='TRC-10 metadata/history limitations; raw quantities preserved'
            elif asset!='TRX':
                reason='Token Transfer log sum differs from account-reported balance; nonstandard/spam token semantics or indexing omissions (cause unconfirmed)'
        elif not matched and t['chain']=='sol':
            missing=t.get('fetch_state',{}).get('missing_transactions',{})
            reason=f'Solana history/discovery gap; {len(missing)} known transaction bodies unavailable; owner metadata/closed-account discovery may be incomplete'
        elif not matched and t['chain']=='bnb':
            reason='Beacon exchange-scale history sampled; full critical windows checked but older native/BEP-2 history is missing, so no zero opening balance can be assumed'
        rows.append({'chain':t['chain'],'address':t['address'],'asset':asset,'symbol':b.get('symbol'),
            'net_transfers':format(net[asset],'f'),'fees':format(fees[asset],'f'),'computed_balance':format(computed,'f'),
            'api_balance':format(observed,'f'),'difference':format(delta,'f'),'within_one_base_unit':matched,
            'cause_or_limit':reason,'balance_raw_ref':b['raw_ref'],
            'timeline_ref':str(timeline_path(t['chain'],t['address']).relative_to(ROOT))})
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/bootstrap/fetch_tron.csv')
    p.add_argument('--additional-addresses',action='append',default=[])
    p.add_argument('--report',default='data/raw/tron/validation.json.gz')
    args=p.parse_args()
    cache={};reports=[];missing=[];schema=[];timelines=[];coverage_errors=[]
    inputs=[args.addresses]+args.additional_addresses
    input_rows={}
    for filename in inputs:
        for row in addresses(filename):input_rows[(row['chain'],row['address'])]=row
    for row in input_rows.values():
        if row['chain'] not in ('trx','xrp','sol','xmr','bnb','unknown'):continue
        path=timeline_path(row['chain'],row['address'])
        if not path.exists():missing.append(row);continue
        t=load(path);timelines.append(t)
        cache={}
        errors=check(t,cache)
        if errors:schema.append({'chain':t['chain'],'address':t['address'],'errors':errors})
        gaps=check_protected_windows(t)
        if gaps:coverage_errors.append({'chain':t['chain'],'address':t['address'],'errors':gaps})
        with localcontext() as ctx:
            ctx.prec=100
            reports.extend(reconcile(t))
    ranked=sorted([t for t in timelines if t['balance_now']],key=lambda t:len(t['txs']),reverse=True)
    sample=ranked[:3]
    sample.extend(sorted(ranked[3:],key=lambda t:(t['chain'],t['address']))[:12])
    sample_keys={(t['chain'],t['address']) for t in sample}
    result={'checked_at':now(),'input':args.addresses,'address_inputs':inputs,
            'input_sha256':{value:hashlib.sha256((ROOT/value).read_bytes()).hexdigest() for value in inputs},
            'timeline_count':len(timelines),'missing_timelines':missing,
            'contract_errors':schema,'protected_window_errors':coverage_errors,
            'counts_by_chain':dict(Counter(t['chain'] for t in timelines)),
            'complete_by_chain':dict(Counter(t['chain'] for t in timelines if t['coverage']['complete'])),
            'events_by_chain':dict(Counter({ch:sum(len(t['txs']) for t in timelines if t['chain']==ch) for ch in {t['chain'] for t in timelines}})),
            'sample_address_count':len(sample),'three_largest_addresses':[{'chain':t['chain'],'address':t['address'],'events':len(t['txs'])} for t in sample[:3]],
            'sample_reconciliations':[r for r in reports if (r['chain'],r['address']) in sample_keys],
            'reconciliations':reports,'balance_checks':len(reports),'balance_matches':sum(r['within_one_base_unit'] for r in reports)}
    save(ROOT/args.report,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('sample_reconciliations','reconciliations','missing_timelines','contract_errors')}))
    print(json.dumps({'missing_timelines':len(missing),'contract_error_addresses':len(schema),
                      'protected_window_error_addresses':len(coverage_errors)}))
    return 1 if schema or missing or coverage_errors else 0

if __name__=='__main__':raise SystemExit(main())
