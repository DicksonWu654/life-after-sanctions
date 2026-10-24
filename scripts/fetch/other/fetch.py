"""Public XRP/Solana history fetcher and explicit untrackable-chain records."""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tron'))
from common import (Client,FetchError,ROOT,addresses,amount,blank,load,merge_txs,now,
                    save,set_bounds,timeline_path,utc)

XRP_SERVERS=['https://xrplcluster.com','https://s1.ripple.com:51234','https://s2.ripple.com:51234']
SOL_SERVERS=['https://api.mainnet-beta.solana.com','https://solana-rpc.publicnode.com','https://solana.drpc.org']
TOKEN_PROGRAMS=['TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb']

def rpc(c,servers,method,params,group,fresh=False,xrp=False):
    errors=[]
    for server in servers:
        body={'method':method,'params':[params]} if xrp else {'jsonrpc':'2.0','id':1,'method':method,'params':params}
        try:
            retry_fresh=fresh
            for attempt in range(4):
                o,r=c.request(server,body,group=group,fresh=retry_fresh)
                result=o.get('result') if isinstance(o,dict) else None
                err=o.get('error') if isinstance(o,dict) else None
                if isinstance(result,dict):err=err or result.get('error')
                rate_error=err in ('tooBusy','slowDown') or (isinstance(err,dict) and err.get('code') in (-32005,429))
                if not rate_error or attempt==3:break
                message=json.dumps(result if xrp else err)
                ms=re.search(r'~(\d+)ms',message)
                delay=min(45,float(ms[1])/1000+1) if ms else 5*2**attempt
                print(f'{method}: rate limit, backing off {delay:.1f}s ({server})',flush=True)
                time.sleep(delay);retry_fresh=True
            result=o.get('result') if isinstance(o,dict) else None
            if not isinstance(o,dict) or o.get('error') or (isinstance(result,dict) and result.get('error')):
                raise FetchError(f'{method} RPC error: {r} {json.dumps(o)[:250]}')
            return result,r
        except FetchError as e:errors.append(str(e))
    raise FetchError('; '.join(errors))

def event(h,block,ts,asset,symbol,dec,delta,fee,parties,ref,eid,kind='balance_change'):
    delta=Decimal(str(delta))
    return {'hash':h,'block':block,'time_utc':ts,'direction':'in' if delta>0 else 'out' if delta<0 else 'self',
            'asset':asset,'symbol':symbol,'decimals':dec,'amount':format(abs(delta),'f'),
            'counterparties':sorted(set(parties)),'fee':str(fee),'raw_ref':ref,'event_id':eid,
            'event_type':kind}

def parse_xrp(entry,addr,ref):
    tx=entry.get('tx',entry.get('tx_json',{}))
    meta=entry.get('meta',{})
    h=tx.get('hash',entry.get('hash'))
    block=tx.get('ledger_index',entry.get('ledger_index'))
    ts=utc((int(tx['date'])+946684800)*1000) if 'date' in tx else None
    fee=Decimal(amount(tx.get('Fee',0))) if tx.get('Account')==addr else Decimal(0)
    delta=Decimal(0)
    parties={tx[k] for k in ('Account','Destination') if tx.get(k) and tx[k]!=addr}
    token_changes=[]
    for node in meta.get('AffectedNodes',[]):
        action,n=next(iter(node.items()))
        fields=n.get('FinalFields',n.get('NewFields',{}))
        previous=n.get('PreviousFields',{})
        if n.get('LedgerEntryType')=='AccountRoot' and fields.get('Account')==addr:
            final=Decimal(str(fields.get('Balance',0)))
            initial=Decimal(str(previous.get('Balance',final)))
            if action=='CreatedNode':initial=Decimal(0)
            if action=='DeletedNode':final=Decimal(0)
            delta+=(final-initial)/10**6
        if n.get('LedgerEntryType')=='RippleState':
            low=fields.get('LowLimit',{}).get('issuer')
            high=fields.get('HighLimit',{}).get('issuer')
            if addr not in (low,high):continue
            final=Decimal(str(fields.get('Balance',{}).get('value','0')))
            initial=Decimal(str(previous.get('Balance',{}).get('value',final)))
            if action=='CreatedNode':initial=Decimal(0)
            if action=='DeletedNode':final=Decimal(0)
            change=(final-initial)*(1 if addr==low else -1)
            currency=fields.get('Balance',{}).get('currency')
            peer=high if addr==low else low
            if change:token_changes.append((currency,peer,change))
    out=[]
    if delta or fee:
        e=event(h,block,ts,'XRP','XRP',6,delta+fee,fee,parties,ref,h+':XRP')
        e['transaction_type']=tx.get('TransactionType')
        e['status']=meta.get('TransactionResult')
        e['balance_delta_including_fee']=format(delta,'f')
        out.append(e)
    for i,(currency,peer,change) in enumerate(token_changes):
        e=event(h,block,ts,f'{currency}:{peer}',currency,None,change,'0',[peer],ref,f'{h}:IOU:{i}')
        e['unit']='XRPL issued currency (decimal precision varies)'
        out.append(e)
    return out

def xrp_one(c,row,args):
    a=row['address'];path=timeline_path('xrp',a)
    old=load(path) if path.exists() else None
    t=old or blank('xrp',a,XRP_SERVERS)
    t['input_raw_ref']=row.get('raw_ref')
    info,ref=rpc(c,XRP_SERVERS,'account_info',{'account':a,'ledger_index':'validated'},'xrp/account_info',fresh=bool(old),xrp=True)
    ledger=info['ledger_index']
    t['balance_now']=[{'asset':'XRP','symbol':'XRP','decimals':6,'amount':amount(info['account_data']['Balance']),
                       'source':load(ROOT/ref)['request']['url']+' account_info','raw_ref':ref+'#/response/result/account_data/Balance',
                       'block':ledger,'as_of':load(ROOT/ref)['requested_at']}]
    lines,lr=rpc(c,XRP_SERVERS,'account_lines',{'account':a,'ledger_index':ledger,'limit':400},'xrp/account_lines',fresh=bool(old),xrp=True)
    for i,line in enumerate(lines.get('lines',[])):
        t['balance_now'].append({'asset':line['currency']+':'+line['account'],'symbol':line['currency'],
             'decimals':None,'amount':line['balance'],'source':load(ROOT/lr)['request']['url']+' account_lines',
             'raw_ref':f'{lr}#/response/result/lines/{i}','block':ledger,'as_of':load(ROOT/lr)['requested_at']})
    state=t.setdefault('fetch_state',{'ledger_min':-1,'ledger_max':ledger,'marker':None,'complete':False,'pages':0})
    if args.refresh and state['complete']:
        state.update(ledger_min=state['ledger_max']+1,ledger_max=ledger,marker=None,complete=False)
    for _ in range(args.max_pages):
        if state['complete']:break
        params={'account':a,'ledger_index_min':state['ledger_min'],'ledger_index_max':state['ledger_max'],
                'limit':200,'forward':True,'binary':False}
        if state['marker']:params['marker']=state['marker']
        # Pagination markers are server-specific; changing backends midstream
        # can silently skip a transaction at a page boundary.
        servers=[state['server']] if state.get('server') else XRP_SERVERS
        result,r=rpc(c,servers,'account_tx',params,'xrp/account_tx',xrp=True)
        state['server']=load(ROOT/r)['request']['url']
        for i,entry in enumerate(result.get('transactions',[])):
            t['txs'].extend(parse_xrp(entry,a,f'{r}#/response/result/transactions/{i}'))
        t['txs']=merge_txs(t['txs'])
        state['marker']=result.get('marker')
        state['pages']+=1
        state['server_ledger_min']=result.get('ledger_index_min')
        state['complete']=not state['marker']
        t['coverage'].update(complete=state['complete'],checked_through_block=state['ledger_max'],
             notes=['XRP flows use exact AccountRoot balance changes with originator fee separated; issued currencies use RippleState changes.',
                    'Counterparties are transaction participants, not an attribution of the economic destination.',
                    'Public server history begins at its reported ledger_index_min; the account creation is present in saved account_tx evidence.'])
        set_bounds(t);save(path,t)
        print(json.dumps({'chain':'xrp','address':a,'pages':state['pages'],'events':len(t['txs']),'complete':state['complete']}),flush=True)
    # A completed default rerun still refreshes the account snapshot. Persist
    # that observation even when no history page was requested.
    set_bounds(t);save(path,t)
    return t

def sol_keys(tx):
    return [a['pubkey'] if isinstance(a,dict) else a for a in tx['transaction']['message']['accountKeys']]

def parse_sol_net(tx,addr,ref,owner_hints=None):
    keys=sol_keys(tx);meta=tx.get('meta') or {}
    h=tx['transaction']['signatures'][0];slot=tx['slot']
    ts=utc(tx['blockTime']*1000) if tx.get('blockTime') is not None else None
    fee=Decimal(amount(meta.get('fee',0),9)) if keys and keys[0]==addr else Decimal(0)
    out=[];owned=set();native_delta=Decimal(0)
    if addr in keys:
        i=keys.index(addr)
        native_delta=Decimal(amount(int(meta['postBalances'][i])-int(meta['preBalances'][i]),9))
    if native_delta or fee:
        changed=[keys[i] for i,(before,after) in enumerate(zip(meta.get('preBalances',[]),meta.get('postBalances',[]))) if before!=after and keys[i]!=addr]
        e=event(h,slot,ts,'SOL','SOL',9,native_delta+fee,fee,changed,ref,h+':SOL')
        e['balance_delta_including_fee']=format(native_delta,'f')
        e['includes_rent_and_account_creation']=True
        e['status']='FAILED' if meta.get('err') else 'SUCCESS'
        out.append(e)
    changes=defaultdict(lambda:{'pre':0,'post':0,'decimals':0,'owner_refs':set()})
    for phase,field in [('pre','preTokenBalances'),('post','postTokenBalances')]:
        for b in meta.get(field,[]) or []:
            token_account=keys[b['accountIndex']]
            hint=(owner_hints or {}).get(token_account)
            owner=b.get('owner') or (hint[0] if hint else None)
            if owner!=addr:continue
            owned.add(token_account)
            mint=b['mint'];ui=b['uiTokenAmount']
            changes[mint][phase]+=int(ui['amount'])
            changes[mint]['decimals']=ui['decimals']
            if not b.get('owner') and hint:changes[mint]['owner_refs'].add(hint[1])
    for mint,b in changes.items():
        delta=Decimal(amount(b['post']-b['pre'],b['decimals']))
        if delta:
            e=event(h,slot,ts,mint,None,b['decimals'],delta,'0',[],ref,h+':SPL:'+mint)
            e['counterparty_note']='Net mint balance change; no owner identity inferred from token account keys'
            if b['owner_refs']:e['owner_resolution_raw_refs']=sorted(b['owner_refs'])
            out.append(e)
    return out,owned

def parse_sol(tx,addr,ref,owner_hints=None):
    """Preserve gross parsed transfers, plus explicit non-payment adjustments.

    Net pre/post balances remain the conservation check. Rent/refunds, owner
    changes and unparsed instructions become labeled adjustments, never guessed
    payment counterparties. Failed transactions contribute only their fee.
    """
    net_rows,owned=parse_sol_net(tx,addr,ref,owner_hints)
    meta=tx.get('meta') or {};keys=sol_keys(tx)
    h=tx['transaction']['signatures'][0];slot=tx['slot']
    ts=utc(tx['blockTime']*1000) if tx.get('blockTime') is not None else None
    token_accounts={}
    for phase in ('preTokenBalances','postTokenBalances'):
        for b in meta.get(phase,[]) or []:
            account=keys[b['accountIndex']]
            hint=(owner_hints or {}).get(account)
            token_accounts[account]={'mint':b['mint'],'decimals':b['uiTokenAmount']['decimals'],
                 'owner':b.get('owner') or (hint[0] if hint else None),
                 'owner_ref':hint[1] if not b.get('owner') and hint else None}
    instructions=[(i,f'{ref}/transaction/message/instructions/{j}',f'outer:{j}')
                  for j,i in enumerate(tx['transaction']['message'].get('instructions',[]))]
    for j,group in enumerate(meta.get('innerInstructions',[]) or []):
        instructions.extend((i,f'{ref}/meta/innerInstructions/{j}/instructions/{k}',f'inner:{j}:{k}')
                            for k,i in enumerate(group.get('instructions',[])))
    flows=[]
    if not meta.get('err'):
        for ins,ir,index in instructions:
            parsed=ins.get('parsed')
            if not isinstance(parsed,dict):continue
            kind=parsed.get('type');info=parsed.get('info',{});program=ins.get('program')
            if program=='system' and kind in ('transfer','transferWithSeed'):
                sender,recipient=info.get('source'),info.get('destination')
                if addr not in (sender,recipient):continue
                value=Decimal(amount(info.get('lamports',0),9))
                delta=value if recipient==addr else -value
                if sender==recipient==addr:delta=Decimal(0)
                e=event(h,slot,ts,'SOL','SOL',9,delta,'0',[a for a in (sender,recipient) if a!=addr],ir,
                        h+':'+index,'system_transfer')
                e.update(amount=format(value,'f'),is_transfer=True,**{'from':sender,'to':recipient})
                flows.append(e)
            elif program in ('spl-token','spl-token-2022') and kind in ('transfer','transferChecked'):
                sender,recipient=info.get('source'),info.get('destination')
                source=token_accounts.get(sender,{});dest=token_accounts.get(recipient,{})
                source_owned=source.get('owner')==addr;dest_owned=dest.get('owner')==addr
                if not source_owned and not dest_owned:continue
                mint=info.get('mint') or source.get('mint') or dest.get('mint')
                decimals=info.get('tokenAmount',{}).get('decimals',source.get('decimals',dest.get('decimals')))
                value=info.get('amount',info.get('tokenAmount',{}).get('amount'))
                if mint is None or decimals is None or value is None:continue
                value=Decimal(amount(value,decimals))
                delta=Decimal(0) if source_owned and dest_owned else value if dest_owned else -value
                parties=[]
                if not source_owned and sender:parties.append(source.get('owner') or sender)
                if not dest_owned and recipient:parties.append(dest.get('owner') or recipient)
                e=event(h,slot,ts,mint,None,decimals,delta,'0',parties,ir,h+':'+index,'spl_transfer')
                e.update(amount=format(value,'f'),is_transfer=True,from_token_account=sender,to_token_account=recipient)
                refs=sorted({b['owner_ref'] for b in (source,dest) if b.get('owner_ref')})
                if refs:e['owner_resolution_raw_refs']=refs
                flows.append(e)
    expected={e['asset']:e for e in net_rows};observed=defaultdict(Decimal)
    for e in flows:
        if e['direction']=='in':observed[e['asset']]+=Decimal(e['amount'])
        elif e['direction']=='out':observed[e['asset']]-=Decimal(e['amount'])
    for asset in set(expected)|set(observed):
        e=expected.get(asset)
        desired=Decimal(0)
        if e and e['direction']!='self':desired=Decimal(e['amount'])*(1 if e['direction']=='in' else -1)
        residual=desired-observed[asset]
        fee=Decimal(e['fee']) if e else Decimal(0)
        if residual or fee:
            if e is None:
                sample=next(r for r in flows if r['asset']==asset)
                e=event(h,slot,ts,asset,sample['symbol'],sample['decimals'],residual,fee,[],ref,h+':adjustment:'+asset)
            else:e=dict(e)
            e.update(amount=format(abs(residual),'f'),direction='in' if residual>0 else 'out' if residual<0 else 'self',
                     is_transfer=False,event_type='balance_adjustment' if residual else 'transaction_fee',
                     event_id=h+':adjustment:'+asset,counterparties=[])
            e['adjustment_note']='Conserves API pre/post balances after parsed transfers and network fee; may include rent/refunds, mint/burn, owner changes or unparsed instructions'
            flows.append(e)
    return flows,owned

def sol_balances(c,t,fresh):
    a=t['address']
    b,r=rpc(c,SOL_SERVERS,'getBalance',[a,{'commitment':'finalized'}],'sol/balances',fresh=fresh)
    t['balance_now']=[{'asset':'SOL','symbol':'SOL','decimals':9,'amount':amount(b['value'],9),
                       'source':load(ROOT/r)['request']['url']+' getBalance','raw_ref':r+'#/response/result/value',
                       'block':b['context']['slot'],'as_of':load(ROOT/r)['requested_at']}]
    state=t.setdefault('fetch_state',{'signature_streams':{},'signatures':{},'processed':[],'missing_transactions':{}})
    state['signature_streams'].setdefault(a,{'before':None,'complete':False,'pages':0})
    for program in TOKEN_PROGRAMS:
        obj,ref=rpc(c,SOL_SERVERS,'getTokenAccountsByOwner',[a,{'programId':program},{'encoding':'jsonParsed','commitment':'finalized'}],
                    'sol/token_accounts',fresh=fresh)
        mint_balances={}
        for i,entry in enumerate(obj.get('value',[])):
            info=entry['account']['data']['parsed']['info'];v=info['tokenAmount'];mint=info['mint']
            state['signature_streams'].setdefault(entry['pubkey'],{'before':None,'complete':False,'pages':0})
            if mint not in mint_balances:
                mint_balances[mint]={'asset':mint,'symbol':None,'decimals':v['decimals'],'amount':'0',
                       'source':load(ROOT/ref)['request']['url']+' getTokenAccountsByOwner','raw_ref':[],
                       'block':obj['context']['slot'],'as_of':load(ROOT/ref)['requested_at']}
            item=mint_balances[mint]
            item['amount']=format(Decimal(item['amount'])+Decimal(amount(v['amount'],v['decimals'])),'f')
            item['raw_ref'].append(f'{ref}#/response/result/value/{i}')
        t['balance_now'].extend(mint_balances.values())
    return b['context']['slot']

def sol_one(c,row,args):
    a=row['address'];path=timeline_path('sol',a)
    old=load(path) if path.exists() else None
    t=old or blank('sol',a,SOL_SERVERS)
    t['input_raw_ref']=row.get('raw_ref')
    slot=sol_balances(c,t,bool(old))
    state=t['fetch_state'];processed=set(state['processed'])
    if args.refresh:
        for s in state['signature_streams'].values():
            if s['complete']:
                s.update(until=s.get('newest'),before=None,complete=False)
    fetched=0
    pages=0
    while True:
        streams=[(account,s) for account,s in state['signature_streams'].items() if not s['complete']]
        for account,s in streams:
            while not s['complete'] and pages<args.max_pages:
                options={'limit':1000,'commitment':'finalized'}
                if s['before']:options['before']=s['before']
                if s.get('until'):options['until']=s['until']
                obj,r=rpc(c,SOL_SERVERS,'getSignaturesForAddress',[account,options],'sol/signatures',
                          fresh=bool(args.refresh and not s['before']))
                if not isinstance(obj,list):raise FetchError('Invalid signatures result '+r)
                if obj and not s['before']:s['newest']=obj[0]['signature']
                for i,entry in enumerate(obj):
                    state['signatures'][entry['signature']]=dict(entry,raw_ref=f'{r}#/response/result/{i}')
                if obj:s['before']=obj[-1]['signature']
                s['pages']+=1;pages+=1
                s['complete']=len(obj)<1000
                save(path,t)
        todo=[sig for sig in state['signatures'] if sig not in processed or sig in state['missing_transactions']]
        for sig in todo:
            if fetched>=args.max_transactions:break
            obj,r=rpc(c,SOL_SERVERS,'getTransaction',[sig,{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':0}],
                      'sol/transactions',fresh=sig in state['missing_transactions'])
            fetched+=1
            if obj is None:
                state['missing_transactions'][sig]={'raw_ref':r,'reason':'Public RPC returned null for historical transaction'}
            else:
                events,owned=parse_sol(obj,a,r+'#/response/result')
                t['txs'].extend(events)
                for account in owned:state['signature_streams'].setdefault(account,{'before':None,'complete':False,'pages':0})
                state['missing_transactions'].pop(sig,None)
            processed.add(sig);state['processed']=sorted(processed)
            t['txs']=merge_txs(t['txs']);set_bounds(t);save(path,t)
            if fetched%25==0:print(json.dumps({'chain':'sol','address':a,'transactions_fetched':fetched,'signatures':len(state['signatures']),'events':len(t['txs'])}),flush=True)
        if fetched>=args.max_transactions or pages>=args.max_pages:break
        if all(s['complete'] for s in state['signature_streams'].values()) and all(sig in processed for sig in state['signatures']):break
    t['coverage'].update(complete=False,signature_history_complete=all(s['complete'] for s in state['signature_streams'].values()),
        checked_through_block=slot,parsed_transactions=len(processed),known_signatures=len(state['signatures']),
        notes=['Parsed System/SPL instruction transfers are individual rows (is_transfer=true). Non-payment balance adjustments and fees are labeled separately (is_transfer=false); adjustments preserve exact pre/post balance conservation and must not be counted as ordinary payments.',
               'Current token accounts and previously closed token accounts discovered in transaction metadata are paged separately, including transfers that do not mention the owner wallet.',
               'Public RPC does not prove discovery of closed token accounts absent from wallet history. coverage.complete remains false for this token-account-discovery gap.',
               f'{len(state["missing_transactions"])} historical transaction bodies returned null; exact signatures and raw refs are in fetch_state.',
               f'{len(state["signatures"])-len(processed)} known signatures remain unparsed; rerun resumes from saved state.'])
    from sol_history import rebuild
    rebuild(t,parse_sol)
    set_bounds(t);save(path,t)
    return t

def bnb_one(c,row,args):
    """Beacon explorer fallback; full critical windows for exchange-scale history."""
    a=row['address'];path=timeline_path('bnb',a)
    old=load(path) if path.exists() else None
    t=old or blank('bnb',a,['https://dex.binance.org','https://explorer.bnbchain.org'])
    t['input_raw_ref']=row.get('raw_ref')
    account,ref=c.get('https://dex.binance.org/api/v1/account/'+a,group='bnb/account',fresh=bool(old))
    if not isinstance(account,dict) or account.get('address')!=a:
        raise FetchError('Invalid Beacon account response '+ref)
    t['balance_now']=[]
    for i,b in enumerate(account.get('balances',[])):
        total=sum((Decimal(b.get(k,'0')) for k in ('free','frozen','locked')),Decimal(0))
        t['balance_now'].append({'asset':b['symbol'],'symbol':b['symbol'],'decimals':8,
             'amount':format(total,'f'),'free':b.get('free'),'frozen':b.get('frozen'),'locked':b.get('locked'),
             'source':'https://dex.binance.org/api/v1/account/'+a,
             'raw_ref':f'{ref}#/response/balances/{i}','as_of':load(ROOT/ref)['requested_at'],
             'snapshot_type':'Legacy Beacon account state; not a current BSC/recovery-contract balance'})
    t['reported_account_sequence']=account.get('sequence')
    # The live explorer frontend identifies /api/v1/txs with address/startTime/
    # endTime/page/rows. dex.binance.org's older history API returns 502.
    # Preserve numeric JSON lexemes and parse them as Decimal for BEP-2 amounts.
    explorer='https://explorer.bnbchain.org/api/v1/txs'
    def page(params):
        obj,r=c.get(explorer,params,group='bnb/explorer-history',preserve_text=True)
        envelope=load(ROOT/r)
        if envelope.get('response_text'):obj=json.loads(envelope['response_text'],parse_float=Decimal)
        if not isinstance(obj,dict) or not isinstance(obj.get('txArray'),list) or 'txNums' not in obj:
            raise FetchError('Invalid Beacon explorer history '+r)
        return obj,r
    sample,sample_ref=page({'address':a,'page':1,'rows':100})
    t['reported_history_records']=sample['txNums']
    events=[]
    def parse_rows(obj,r):
        for i,tx in enumerate(obj['txArray']):
            sender,recipient=tx.get('fromAddr'),tx.get('toAddr')
            if a not in (sender,recipient):
                # Multi-send parents may omit the child participant. Preserve
                # them in raw evidence; do not invent a wallet-level amount.
                continue
            h=tx['txHash'];asset=tx.get('txAsset') or 'BNB';value=Decimal(str(tx.get('value') or 0))
            raw=f'{r}#/response/txArray/{i}'
            parties=[v for v in (sender,recipient) if v and v!=a]
            if tx.get('code',0)==0 and tx.get('txType') in ('TRANSFER','CROSS_TRANSFER_OUT','CROSS_TRANSFER_IN') and not tx.get('hasChildren') and value:
                delta=Decimal(0) if sender==recipient==a else value if recipient==a else -value
                e=event(h,tx.get('blockHeight'),utc(tx['timeStamp']),asset,asset,8,delta,'0',parties,raw,h+':transfer','beacon_transfer')
                e.update(amount=format(value,'f'),is_transfer=True,transaction_type=tx.get('txType'),**{'from':sender,'to':recipient})
                events.append(e)
            if sender==a:
                fee=Decimal(str(tx.get('txFee') or 0))
                e=event(h,tx.get('blockHeight'),utc(tx['timeStamp']),'BNB','BNB',8,0,fee,[],raw,h+':fee','transaction_fee')
                e['is_transfer']=False;events.append(e)
    parse_rows(sample,sample_ref)
    second,second_ref=page({'address':a,'page':2,'rows':100})
    parse_rows(second,second_ref)
    sample_rows=sample['txArray']+second['txArray']
    t['sample_raw_refs']=[sample_ref,second_ref]
    from datetime import timedelta
    current=datetime.now(timezone.utc)
    listed_dates=set([row['first_listed_date']]) if row.get('first_listed_date') else set()
    import csv
    ledger=ROOT/'data/ledger.csv'
    if ledger.exists():
        for record in csv.DictReader(ledger.open()):
            if (record.get('address_normalized') or record.get('address'))==a and record.get('listed_date'):
                listed_dates.add(record['listed_date'])
    windows=[('latest_90_days',current-timedelta(days=90),current)]
    for date in sorted(listed_dates):
        listed=datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        windows.append(('designation_'+date,listed-timedelta(days=60),min(current,listed+timedelta(days=400))))
    priorities=t.setdefault('priority_windows',{})
    for label,start,end in windows:
        if priorities.get(label,{}).get('complete') and not args.refresh:continue
        state={'from_time':start.isoformat(),'to_time':end.isoformat(),'pages':0,'total_records':None,'complete':False,'raw_refs':[]}
        for number in range(1,args.max_pages+1):
            params={'address':a,'rows':100,'page':number,'startTime':int(start.timestamp()*1000),'endTime':int(end.timestamp()*1000)}
            response,r=page(params);parse_rows(response,r)
            state['pages']+=1;state['raw_refs'].append(r);state['total_records']=response['txNums']
            if number*100>=response['txNums'] or len(response['txArray'])<100:
                state['complete']=True;break
        priorities[label]=state
    doc='https://docs.bnbchain.org/bc-fusion/overview/'
    content,doc_ref=c.get(doc,group='bnb/docs')
    t['txs']=merge_txs(t.get('txs',[])+events)
    oldest_sample=min((tx['blockHeight'] for tx in sample_rows),default=385251927)
    t['coverage'].update(complete=False,chain_shutdown_block=385251927,chain_shutdown_date='2024-12-03',
        shutdown_source_url=doc,shutdown_raw_ref=doc_ref,
        huge_address=True,reported_history_records=sample['txNums'],history_count_raw_ref=sample_ref,
        priority_windows_complete=all(w['complete'] for w in priorities.values()),
        designation_dates_available=bool(listed_dates),
        missing_intervals=[{'from_block':0,'to_block':oldest_sample,'assets':'BNB and all BEP-2 assets',
                           'reason':'Exchange-scale full history not fetched; only latest 200 explorer records and full critical windows queried'}],
        notes=['This is BNB Beacon Chain (bnb1 bech32), separate from BSC/EVM.',
               'Official documentation says Beacon Chain shut down at block 385251927 on 2024-12-03. Legacy dex history/head/time APIs fail; explorer /api/v1/txs remains available and its address filter was independently checked.',
               f'Explorer reports {sample["txNums"]} address history records. Full retrieval is not feasible in this keyless shared-budget pass; exact missing block range is recorded. Latest 200 records are retained, with native and BEP-2 transfers and originator fees separated.',
               'Full T-60..T+400 (clipped at fetch time) windows for each known designation and the latest 90 days are queried. These dates are after the documented chain shutdown; empty windows are backed by explicit explorer responses, not assumed.',
               'Multi-send parent records with children are retained in raw responses but not treated as single wallet transfers; older multi-send history remains within the missing range.',
               'The account snapshot is not proof of current spendability or asset-recovery balances on BSC. No recovery claim or transaction is attempted.'])
    set_bounds(t);save(path,t)
    return t

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/bootstrap/fetch_tron.csv')
    p.add_argument('--refresh',action='store_true')
    p.add_argument('--chain',choices=['sol','xrp','xmr','bnb','unknown'])
    p.add_argument('--max-pages',type=int,default=1000)
    p.add_argument('--max-transactions',type=int,default=20000)
    p.add_argument('--delay',type=float,default=.7)
    args=p.parse_args()
    c=Client(source='other',delay=args.delay,retries=2)
    rows=[r for r in addresses(args.addresses) if r['chain'] in ('sol','xrp','xmr','bnb','unknown') and (not args.chain or r['chain']==args.chain)]
    failures=[]
    for row in rows:
        chain,a=row['chain'],row['address'];path=timeline_path(chain,a)
        try:
            if chain=='xrp':t=xrp_one(c,row,args)
            elif chain=='sol':t=sol_one(c,row,args)
            elif chain=='bnb':t=bnb_one(c,row,args)
            else:
                t=blank(chain,a,row.get('source_url') or ('Input address list: '+args.addresses))
                t['input_raw_ref']=row.get('raw_ref')
                t['coverage']['notes']=['Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys.' if chain=='xmr' else
                    'USDT ticker entry uses a Bitcoin-format address. Token network is not specified by the bootstrap; Omni-layer history is not fetched by this non-UTXO worker. Do not interpret absent transfers as no activity.']
                t['coverage']['untrackable']=chain=='xmr'
                save(path,t)
            print(json.dumps({'chain':chain,'address':a,'events':len(t['txs']),'complete':t['coverage']['complete']}),flush=True)
        except Exception as e:
            failures.append({'chain':chain,'address':a,'error':str(e)})
            t=load(path) if path.exists() else blank(chain,a, SOL_SERVERS if chain=='sol' else XRP_SERVERS)
            t['coverage']['complete']=False;t['coverage']['notes'].append(type(e).__name__+': '+str(e))
            save(path,t)
            print(json.dumps({'chain':chain,'address':a,'error':str(e)}),flush=True)
    save(ROOT/'data/raw/other/run-summary.json.gz',{'fetched_at':now(),'addresses':len(rows),'network_calls':c.calls,'cache_hits':c.hits,'http_errors':c.errors,'failures':failures})
    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
