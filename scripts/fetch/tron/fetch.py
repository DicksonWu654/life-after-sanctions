"""Resumable confirmed Tron native/TRC-20 history; no private API credentials.

Use --addresses data/addresses.csv unchanged once the primary ledger exists.
Each response is immutable evidence; cursors and completed time ranges live in the
timeline so an interrupted run resumes without replaying completed requests.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from collections import Counter
from common import (Client, FetchError, ROOT, addresses, amount, blank, load,
                    merge_txs, now, save, set_bounds, timeline_path, utc,acquire_address_lock,BusyAddress,missing)

API = 'https://api.trongrid.io'
HEAD_API = API+'/walletsolidity/getnowblock'
SCAN = 'https://apilist.tronscanapi.com'
USDT = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def decode58(addr):
    n = 0
    for ch in addr:
        n = n * 58 + B58.index(ch)
    b = n.to_bytes(25, 'big')
    if hashlib.sha256(hashlib.sha256(b[:-4]).digest()).digest()[:4] != b[-4:]:
        raise ValueError('Invalid Tron address checksum')
    return b[:-4]

def encode58(addr):
    if not addr:
        return None
    if addr.startswith('T'):
        return addr
    b = bytes.fromhex(addr)
    b += hashlib.sha256(hashlib.sha256(b).digest()).digest()[:4]
    n = int.from_bytes(b, 'big')
    out = ''
    while n:
        n, rem = divmod(n, 58)
        out = B58[rem] + out
    return out

def direction(addr, sender, recipient):
    if sender == recipient == addr:
        return 'self'
    return 'out' if sender == addr else 'in'

def base_event(txhash, block, ms, asset, symbol, decimals, value, sender, recipient, addr, ref, event_id):
    return {'hash':txhash, 'block':block, 'time_utc':utc(ms),
            'direction':direction(addr,sender,recipient), 'asset':asset, 'symbol':symbol,
            'decimals':decimals, 'amount':amount(value,decimals),
            'counterparties':sorted({a for a in (sender,recipient) if a and a != addr}),
            'from':sender, 'to':recipient, 'fee':'0', 'raw_ref':ref, 'event_id':event_id}

def parse_native(tx, addr, ref, fee_resolution=None):
    out, types = [], []
    h, block, ms = tx['txID'], tx.get('blockNumber'), tx['block_timestamp']
    contracts = tx.get('raw_data', {}).get('contract', [])
    success = all(r.get('contractRet','SUCCESS') == 'SUCCESS' for r in tx.get('ret',[]))
    payer = None
    for i, contract in enumerate(contracts):
        kind = contract['type']
        types.append(kind)
        v = contract.get('parameter',{}).get('value',{})
        sender = encode58(v.get('owner_address'))
        payer = payer or sender
        recipient = encode58(v.get('to_address') or v.get('contract_address'))
        value = v.get('amount') if kind == 'TransferContract' else v.get('call_value') if kind == 'TriggerSmartContract' else None
        if value is not None and success and addr in (sender,recipient):
            out.append(base_event(h,block,ms,'TRX','TRX',6,value,sender,recipient,addr,ref,f'{h}:native:{i}'))
        # TRC-10 metadata (including decimals) is joined from the account response
        # later. Never silently interpret raw token quantities as TRX.
        if kind == 'TransferAssetContract' and success and addr in (sender,recipient):
            asset = str(v.get('asset_name',''))
            if asset.startswith('3130'):
                try: asset = bytes.fromhex(asset).decode()
                except (ValueError,UnicodeDecodeError): pass
            event = base_event(h,block,ms,'trc10:'+asset,asset,0,v.get('amount',0),sender,recipient,addr,ref,f'{h}:trc10:{i}')
            event['raw_amount'] = str(v.get('amount',0))
            event['decimals_known'] = False
            out.append(event)
    # Only the originator pays the top-level fee; include non-payment operations
    # and failed contract calls without inventing a successful token transfer.
    if payer == addr:
        fee = sum(int(r.get('fee',0)) for r in tx.get('ret',[]))
        event = base_event(h,block,ms,'TRX','TRX',6,0,addr,addr,addr,ref,h+':fee')
        event.update(fee=amount(fee), event_type='transaction_fee', contract_types=types,
                     status='SUCCESS' if success else 'FAILED')
        if fee_resolution:
            event.update(fee=amount(fee_resolution['fee_sun']),fee_raw_ref=fee_resolution['raw_ref'],
                         indexed_fee_sun=str(fee))
        out.append(event)
    return out, types

def parse_internal(row, addr, ref):
    data = row.get('data',{})
    if data.get('rejected'):
        return []
    sender,recipient = encode58(row.get('from_address')),encode58(row.get('to_address'))
    if addr not in (sender,recipient):
        return []
    values = data.get('call_value_info',data.get('callValueInfo',[]))
    # TronGrid's current schema maps '_' to native SUN and TRC-10 IDs
    # to raw token quantities. Older schemas used callValueInfo arrays.
    if isinstance(data.get('call_value'),dict):
        values = [{'callValue':v,'tokenId':None if k=='_' else k} for k,v in data['call_value'].items()]
    if isinstance(values,dict):values=[values]
    out=[]
    for i,val in enumerate(values):
        value=val.get('callValue',val.get('call_value',0))
        token=val.get('tokenId',val.get('token_id'))
        if value and not token:
            out.append(base_event(row['tx_id'],row.get('blockNumber'),row['block_timestamp'],'TRX','TRX',6,
                       value,sender,recipient,addr,ref,f'{row["tx_id"]}:internal:{row["internal_tx_id"]}:{i}'))
    return out

def token_resolution_key(t):
    return hashlib.sha256(json.dumps([t['transaction_id'],t.get('from'),t.get('to'),str(t.get('value'))]).encode()).hexdigest()

def resolve_token(c,t,row):
    key=token_resolution_key(row)
    stored=t.setdefault('token_resolution',{})
    if key in stored:return stored[key]
    h=row['transaction_id']
    try:
        receipt,ref=c.request(API+'/wallet/gettransactioninfobyid',{'value':h},group='receipts')
        matches=[]
        topic='ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
        for i,log in enumerate(receipt.get('log',[])):
            topics=log.get('topics',[])
            if len(topics)!=3 or topics[0].lower()!=topic:continue
            sender=encode58('41'+topics[1][-40:]);recipient=encode58('41'+topics[2][-40:])
            value=int(log.get('data') or '0',16)
            if sender==row.get('from') and recipient==row.get('to') and value==int(row.get('value','0')):
                contract=log['address'];contract=contract if len(contract)==42 else '41'+contract
                matches.append((encode58(contract),i))
        contracts={a for a,_ in matches}
        if len(contracts)!=1:raise ValueError(f'{len(contracts)} matching token contracts in receipt {ref}')
        asset,index=matches[0]
        result={'address':asset,'blockNumber':receipt.get('blockNumber'),
                'asset_raw_ref':f'{ref}#/response/log/{index}','block_raw_ref':ref+'#/response/blockNumber'}
        b=next((b for b in t['balance_now'] if b['asset']==asset),None)
        if b:
            result.update(decimals=b['decimals'],symbol=b['symbol'],metadata_raw_ref=b['raw_ref'])
        else:
            obj,dr=c.request(API+'/wallet/triggerconstantcontract',{'owner_address':t['address'],
                    'contract_address':asset,'function_selector':'decimals()','visible':True},group='token_metadata')
            values=obj.get('constant_result',[])
            if values:
                result.update(decimals=int(values[0],16),symbol=None,metadata_raw_ref=dr+'#/response/constant_result/0')
            elif int(row.get('value','0'))==0:
                result.update(decimals=0,symbol=None,decimals_known=False)
            else:raise ValueError('Missing token decimals '+dr)
        stored[key]=result
        return result
    except (FetchError,ValueError,KeyError) as e:
        item={'hash':h,'raw_ref':row.get('_raw_ref'),'reason':str(e)}
        unresolved=t.setdefault('unresolved_events',[])
        if item not in unresolved:unresolved.append(item)
        return None

def parse_trc20(t, addr, ref, ordinal=0, resolution=None):
    indexed=t.get('token_info') or {}
    token = indexed if indexed.get('address') else resolution or {'address':'unresolved_token:'+t['transaction_id'],'decimals':0,'symbol':None}
    decimals = int(token.get('decimals',0))
    signature = [t['transaction_id'],token['address'],t.get('from'),t.get('to'),str(t.get('value')),t.get('type')]
    eid = hashlib.sha256(json.dumps(signature).encode()).hexdigest() + ':' + str(ordinal)
    event = base_event(t['transaction_id'],t.get('blockNumber'),t['block_timestamp'],token['address'],
                       token.get('symbol'),decimals,t.get('value','0'),t.get('from'),t.get('to'),addr,ref,eid)
    event['event_type'] = t.get('type','Transfer')
    if not indexed.get('address'):
        event['metadata_missing_in_indexer']=True
        event['raw_amount']=str(t.get('value','0'))
        if resolution:
            event['block']=resolution.get('blockNumber')
            for field in ('asset_raw_ref','metadata_raw_ref','block_raw_ref'):
                if resolution.get(field):event[field]=resolution[field]
            event['decimals_known']=resolution.get('decimals_known',True)
        else:
            event.update(decimals=None,decimals_known=False,amount_is_raw_units=True)
    return event

def fetch_balances(c, t, fresh=False, labels=True):
    a = t['address']
    errors, balances = [], {}
    try:
        account, ref = c.request(API+'/wallet/getaccount', {'address':a,'visible':True},group='accounts',fresh=fresh)
        if not isinstance(account,dict) or account.get('Error'):
            raise FetchError(f'getaccount invalid response: {ref}')
        if not account or account.get('address') == a:
            balances['TRX'] = {'asset':'TRX','symbol':'TRX','decimals':6,'amount':amount(account.get('balance',0)),
                               'source':API+'/wallet/getaccount','raw_ref':ref+'#/response',
                               'as_of':load(ROOT/ref)['requested_at'],
                               'zero_balance_field_omitted': 'balance' not in account}
        t['account_state'] = {'raw_ref':ref, 'frozen':account.get('frozen'), 'frozenV2':account.get('frozenV2'),
                              'unfrozenV2':account.get('unfrozenV2'), 'account_resource':account.get('account_resource')}
    except (FetchError,ValueError) as e:
        errors.append(str(e))
    scan = None
    if labels:
        try:
            scan, ref = c.get(SCAN+'/api/account',{'address':a},group='labels',fresh=fresh)
            if not isinstance(scan,dict) or scan.get('address') != a:
                raise FetchError(f'TronScan invalid account: {ref}')
            t['labels_raw_ref'] = ref
            t['labels'] = {key:scan[key] for key in ('name','addressTag','addressTagLogo','publicTag','tags','risk') if key in scan}
            t['reported_transaction_counts'] = {k:scan.get(k) for k in ('totalTransactionCount','transactions','transactions_in','transactions_out')}
            for field in ('tokenBalances','trc20token_balances'):
                for i,b in enumerate(scan.get(field,[])):
                    asset = b.get('tokenId')
                    if not asset or asset == '_':
                        continue
                    if b.get('tokenType') == 'trc10' or asset.isdigit():
                        asset = 'trc10:'+asset
                    dec = int(b.get('tokenDecimal',0))
                    balances[asset] = {'asset':asset,'symbol':b.get('tokenAbbr'),'decimals':dec,
                                       'amount':amount(b.get('balance',0),dec), 'source':SCAN+'/api/account',
                                       'raw_ref':f'{ref}#/response/{field}/{i}',
                                       'as_of':load(ROOT/ref)['requested_at']}
        except (FetchError,ValueError) as e:
            errors.append(str(e))
    # USDT balanceOf must be queried even for unactivated/frozen accounts.
    try:
        parameter = decode58(a)[1:].hex().rjust(64,'0')
        payload = {'owner_address':a,'contract_address':USDT,'visible':True,
                   'function_selector':'balanceOf(address)','parameter':parameter}
        obj, ref = c.request(API+'/wallet/triggerconstantcontract',payload,group='balances',fresh=fresh)
        values = obj.get('constant_result',[]) if isinstance(obj,dict) else []
        if not values:
            raise FetchError(f'USDT balanceOf missing result: {ref}')
        balances[USDT] = {'asset':USDT,'symbol':'USDT','decimals':6,'amount':amount(int(values[0],16)),
                          'source':API+'/wallet/triggerconstantcontract balanceOf(address)',
                          'raw_ref':ref+'#/response/constant_result/0',
                          'as_of':load(ROOT/ref)['requested_at'],'at_latest_block':True}
    except (FetchError,ValueError) as e:
        errors.append(str(e))
    if balances:
        t['balance_now'] = list(balances.values())
    t['balance_errors'] = errors
    t['balance_checked_at'] = now()
    return scan

def run_stream(c, t, name, path, budget, state=None):
    state = t['fetch_state'][name] if state is None else state
    used = 0
    by_id={e['event_id']:e for e in t['txs']}
    def checkpoint():
        t['txs']=merge_txs(list(by_id.values()))
        set_bounds(t);save(path,t)
    while state['pending'] and used < budget:
        win = state['pending'][0]
        params = {'limit':200,'only_confirmed':'true','order_by':'block_timestamp,asc',
                  'min_timestamp':win['lo'],'max_timestamp':win['hi']}
        if win.get('cursor'):
            params['fingerprint'] = win['cursor']
        suffix = {'trc20':'/transactions/trc20','native':'/transactions','internal':'/internal-transactions'}[name]
        try:
            obj, ref = c.get(f'{API}/v1/accounts/{t["address"]}{suffix}',params,group=name)
            used += 1
            if not isinstance(obj,dict) or obj.get('success') is not True or not isinstance(obj.get('data'),list):
                # A transient HTTP-200 API error must not poison the resumable
                # cache forever. Keep the old response and retry immutably.
                obj,ref=c.get(f'{API}/v1/accounts/{t["address"]}{suffix}',params,group=name,fresh=True)
                if not isinstance(obj,dict) or obj.get('success') is not True or not isinstance(obj.get('data'),list):
                    raise FetchError(f'Invalid {name} response: {ref}')
        except FetchError as e:
            state['error'] = str(e)
            # Cursors expire. Restart the exact inclusive time window with its
            # immutable cached first page; splitting prevents repeating the cap.
            if win.get('cursor') and win['hi'] > win['lo']:
                split_window(state,win)
                checkpoint()
                continue
            checkpoint()
            break
        data = obj['data']
        page_events=[]
        occurrences = Counter()
        for i,row in enumerate(data):
            raw = f'{ref}#/response/data/{i}'
            if name == 'native':
                events, types = parse_native(row,t['address'],raw,t.get('fee_resolution',{}).get(row['txID']))
                t['contract_types'].update(types)
                page_events.extend(events)
            elif name == 'internal':
                page_events.extend(parse_internal(row,t['address'],raw))
            else:
                if row.get('type','Transfer') != 'Transfer':
                    continue
                signature = json.dumps(row,sort_keys=True)
                ordinal = occurrences[signature]
                occurrences[signature] += 1
                resolution=None
                if not (row.get('token_info') or {}).get('address'):
                    row=dict(row,_raw_ref=raw)
                    resolution=resolve_token(c,t,row)
                page_events.append(parse_trc20(row,t['address'],raw,ordinal,resolution))
        by_id.update((e['event_id'],e) for e in page_events)
        state['pages_fetched'] += 1
        state['rows_fetched'] += len(data)
        state['error'] = None
        win['pages'] = win.get('pages',0) + 1
        cursor = obj.get('meta',{}).get('fingerprint')
        next_link = obj.get('meta',{}).get('links',{}).get('next')
        if not cursor and next_link:
            import urllib.parse
            cursor = urllib.parse.parse_qs(urllib.parse.urlsplit(next_link).query).get('fingerprint',[None])[0]
        if cursor and data and cursor != win.get('cursor') and win['pages'] < 5:
            win['cursor'] = cursor
        elif (cursor and data) or (win['pages'] >= 5 and len(data) == 200):
            last_ms=max((r['block_timestamp'] for r in data),default=win['lo'])
            if last_ms > win['lo']:
                # Ascending pages prove all timestamps strictly below the last
                # row. Requery the boundary millisecond inclusively so events
                # sharing that timestamp cannot be lost at a provider cap.
                state['ranges'].append({'from_ms':win['lo'],'to_ms':last_ms-1,
                    'terminal_raw_ref':ref,'boundary_requeried_inclusively':True})
                state['pending'][0]={'lo':last_ms,'hi':win['hi']}
                state['splits']=state.get('splits',0)+1
            elif win['hi'] > win['lo']:
                split_window(state,win)
            else:
                state.setdefault('gaps',[]).append({'from_ms':win['lo'],'to_ms':win['hi'],
                    'reason':'More than one endpoint page/cap at a single millisecond; cannot split safely'})
                state['pending'].pop(0)
        else:
            state['ranges'].append({'from_ms':win['lo'],'to_ms':win['hi'],'terminal_raw_ref':ref})
            state['pending'].pop(0)
        state['complete'] = not state['pending'] and not state.get('gaps')
        interval=1 if len(by_id)<10000 else 5 if len(by_id)<100000 else 25
        if used%interval==0 or not state['pending']:
            checkpoint()
        if used%25==0:
            print(json.dumps({'address':t['address'],'stream':name,'pages_this_pass':used,
                             'pages_total':state['pages_fetched'],'events':len(by_id)}),flush=True)
    if used:checkpoint()
    return used

def split_window(state,win):
    mid = (win['lo']+win['hi'])//2
    state['pending'][0:1] = [{'lo':win['lo'],'hi':mid},{'lo':mid+1,'hi':win['hi']}]
    state['splits'] = state.get('splits',0)+1

def init_stream(lo,hi):
    return {'pending':[{'lo':lo,'hi':hi}], 'ranges':[], 'complete':False,'pages_fetched':0,'rows_fetched':0}

def normalize_trc10(t):
    balances = {b['asset']:b for b in t['balance_now']}
    blocks={e['hash']:(e['block'],e['raw_ref']) for e in t['txs'] if e.get('block') is not None}
    for event in t['txs']:
        if event.get('block') is None and event['hash'] in blocks:
            event['block'],event['block_raw_ref']=blocks[event['hash']]
        if event['asset'].startswith('trc10:'):
            b = balances.get(event['asset'])
            if b:
                event['decimals'],event['symbol'] = b['decimals'],b['symbol']
                event['amount'] = amount(event['raw_amount'],b['decimals'])
                event['decimals_known'] = True
                event['metadata_raw_ref'] = b['raw_ref']

def known_ranges(t,name):
    rows=list(t['fetch_state'][name]['ranges'])
    rows.extend(r for window in t.get('priority_windows',{}).values() for r in window.get(name,{}).get('ranges',[]))
    rows.extend(t.get('gap_repair',{}).get(name,{}).get('ranges',[]))
    return list({(r['from_ms'],r['to_ms'],r.get('terminal_raw_ref')):r for r in rows}.values())

def absorb_incremental(parent,state):
    if not state or state.get('merged'):return
    parent['ranges'].extend(state['ranges'])
    for window in state['pending']:
        if window not in parent['pending']:parent['pending'].append(dict(window))
    for key in ('pages_fetched','rows_fetched'):parent[key]+=state[key]
    for gap in state.get('gaps',[]):
        if gap not in parent.setdefault('gaps',[]):parent['gaps'].append(gap)
    state['merged']=True

def prepare_incremental(t,hi,legacy_buffer):
    previous=t.get('incremental_refresh',{});fresh={}
    for name,parent in t['fetch_state'].items():
        # Interrupted batches persist their range proofs in the timeline too.
        absorb_incremental(parent,previous.get(name))
        boundary=max([r['to_ms'] for r in known_ranges(t,name)]+[0])
        state=init_stream(max(0,boundary-legacy_buffer),hi)
        if hi<=boundary:state.update(pending=[],complete=True)
        fresh[name]=state
    t['incremental_refresh']=fresh

def merge_incremental(t,hi):
    for name,parent in t['fetch_state'].items():
        state=t['incremental_refresh'][name]
        old_pending=list(parent['pending'])
        absorb_incremental(parent,state)
        ranges=known_ranges(t,name)
        target=max([hi]+[w['hi'] for w in old_pending]+[r['to_ms'] for r in ranges])
        remaining=missing([(r['from_ms'],r['to_ms']) for r in ranges],0,target)
        resumable={(w['lo'],w['hi']):w for w in old_pending+state['pending']}
        parent.update(ranges=ranges,pending=[resumable.get((lo,end),{'lo':lo,'hi':end}) for lo,end in remaining],
                      complete=not remaining and not parent.get('gaps'),error=state.get('error'))
        t['coverage'].setdefault('missing_time_windows',{})[name]=[{'from_ms':lo,'to_ms':end} for lo,end in remaining]

def fetch_one(c,row,args,head):
    addr = row['address']
    path = timeline_path('trx',addr)
    old = load(path) if path.exists() else None
    t = old or blank('trx',addr,[API,SCAN])
    t['input_raw_ref'] = row.get('raw_ref')
    t['contract_types'] = Counter(t.get('contract_types',{}))
    # Share a nearby confirmed head across addresses. Rebinding a local dict
    # left the caller's head expired and caused one redundant RPC per address.
    # Balances retain their own observation timestamps; this head is <=60s old.
    if (not old or args.refresh) and time.monotonic()-head.get('_observed',0)>60:
        obj,ref=c.request(HEAD_API,{},group='head',fresh=True)
        head.update(obj['block_header']['raw_data'],raw_ref=ref,_observed=time.monotonic())
    hi = head['timestamp']
    if 'fetch_state' not in t:
        t['fetch_state'] = {name:init_stream(0,hi) for name in ('native','trc20','internal')}
        t['coverage']['history_head_finality']='solid'
    t['fetch_state'].setdefault('internal',init_stream(0,hi))
    partial_refresh=bool(args.refresh and old and any(not s['complete'] for s in t['fetch_state'].values()))
    if args.refresh and old:
        legacy_buffer=0 if t['coverage'].get('history_head_finality') in ('solid','solid_revalidated') else 120000
        if partial_refresh:prepare_incremental(t,hi,legacy_buffer)
        else:
            for state in t['fetch_state'].values():
                prev_hi = max([r['to_ms'] for r in state['ranges']] + [w['hi'] for w in state['pending']] + [0])
                if hi > prev_hi:
                    # Same-block timestamps are re-read and event IDs deduplicate.
                    state['pending'].append({'lo':max(0,prev_hi-legacy_buffer),'hi':hi})
                    state['complete'] = False
    if any(not s['complete'] for s in t['fetch_state'].values()):t['coverage']['complete']=False
    continuing=old and any(not s['complete'] for s in t['fetch_state'].values()) and t.get('balance_now') and not args.refresh
    if not args.history_only and not continuing:
        fetch_balances(c,t,fresh=bool(old),labels=not args.no_labels)
        save(path,t)
    for name in ('native','trc20','internal'):
        run_stream(c,t,name,path,args.max_pages,state=t['incremental_refresh'][name] if partial_refresh else None)
    if partial_refresh:merge_incremental(t,hi)
    normalize_trc10(t)
    state = t['fetch_state']
    if args.refresh and all(s['complete'] for s in state.values()):t['coverage']['history_head_finality']='solid'
    requested_hi=min(max([r['to_ms'] for r in s['ranges']]+[w['hi'] for w in s['pending']]+[0]) for s in state.values())
    t['coverage'].update({
        'history_start_requested_ms':0,
        'checked_through_block':head['number'] if requested_hi==hi else t['coverage'].get('checked_through_block'),
        'checked_through_time':utc(requested_hi), 'head_raw_ref':head['raw_ref'],
        'native_transactions_complete':state['native']['complete'],
        'trc20_transfers_complete':state['trc20']['complete'],
        'internal_transactions_complete':state['internal']['complete'],
        'complete':all(s['complete'] for s in state.values()) and not t.get('unresolved_events'),
        'unresolved_event_count':len(t.get('unresolved_events',[])),
        'notes':[
            'Confirmed direct native transactions and all TRC-20 Transfer events are paged separately.',
            'TronGrid TRC-20 responses omit block numbers/log indexes; available native, receipt or TronScan evidence supplies blocks, otherwise they remain null.',
            'Internal TRX transfers are independently paged at /internal-transactions; rejected calls and zero-value calls are excluded from flows.',
            'TRC-10 decimals are known only when an account token metadata entry supplies them; raw_amount is preserved.',
            'USDT issuer burn operations may change balance without a Transfer event; reconciliation must not assume a mismatch means an unobserved payment.'
        ]})
    for name,s in state.items():
        if s['pending']:
            t['coverage']['notes'].append(f'{name}: {len(s["pending"])} unfinished time windows remain; run without --refresh to resume older gaps. Exact windows are in fetch_state.')
        if s.get('error'):
            t['coverage']['notes'].append(f'{name}: '+s['error'])
    set_bounds(t)
    save(path,t)
    return t

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/bootstrap/fetch_tron.csv')
    p.add_argument('--refresh',action='store_true')
    p.add_argument('--max-pages',type=int,default=500,help='Per stream/address per invocation; pending windows are persisted')
    p.add_argument('--limit',type=int)
    p.add_argument('--address',action='append',help='Fetch only selected addresses from the input CSV')
    p.add_argument('--exclude-address',action='append',default=[],help='Exclude addresses owned by another active writer')
    p.add_argument('--offset',type=int,default=0)
    p.add_argument('--delay',type=float,default=1.2)
    p.add_argument('--history-only',action='store_true',help='Use existing balances; useful during interrupted-history repair')
    p.add_argument('--only-incomplete',action='store_true',help='Skip addresses whose three history streams already exhausted')
    p.add_argument('--no-labels',action='store_true')
    args=p.parse_args()
    c=Client(delay=args.delay)
    head_obj,ref=c.request(HEAD_API,{},group='head',fresh=True)
    head=dict(head_obj['block_header']['raw_data'],raw_ref=ref,_observed=time.monotonic())
    rows=[r for r in addresses(args.addresses) if r['chain']=='trx'][args.offset:]
    if args.limit is not None:rows=rows[:args.limit]
    if args.address:rows=[r for r in rows if r['address'] in args.address]
    rows=[r for r in rows if r['address'] not in args.exclude_address]
    if args.only_incomplete:
        def needs_work(row):
            path=timeline_path('trx',row['address'])
            if not path.exists():return True
            t=load(path)
            return not t.get('fetch_state') or not all(s.get('complete') for s in t['fetch_state'].values())
        rows=[r for r in rows if needs_work(r)]
    failures=[]
    for i,row in enumerate(rows,1):
        try:
            with acquire_address_lock('trx',row['address']):
                t=fetch_one(c,row,args,head)
            status={k:s['complete'] for k,s in t['fetch_state'].items()}
            print(json.dumps({'i':i,'of':len(rows),'address':row['address'],'events':len(t['txs']),
                  'streams_complete':status,'network_calls':c.calls,'cache_hits':c.hits}),flush=True)
        except BusyAddress as e:
            print(json.dumps({'i':i,'address':row['address'],'skipped_active_writer':str(e)}),flush=True)
        except Exception as e:
            failures.append({'address':row['address'],'error':str(e)})
            path=timeline_path('trx',row['address'])
            t=load(path) if path.exists() else blank('trx',row['address'],API)
            t['coverage']['complete']=False
            t['coverage']['notes'].append(type(e).__name__+': '+str(e))
            save(path,t)
            print(json.dumps({'i':i,'address':row['address'],'error':str(e)}),flush=True)
    save(ROOT/'data/raw/tron/run-summary.json.gz',{'fetched_at':now(),'addresses':len(rows),'network_calls':c.calls,
         'cache_hits':c.hits,'http_errors':c.errors,'failures':failures})
    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
