"""Resolve old SPL owner omissions from explicit on-chain initialization history.

Current ownership alone is never projected backward. Ownership hints are seeded
by initializeAccount/create instructions or same/earlier transaction metadata,
and updated by accountOwner setAuthority instructions in chronological order.
"""
from common import ROOT,load,merge_txs

def rebuild(t,parser):
    wanted=set(t['fetch_state']['processed'])
    transactions={}
    for path in (ROOT/'data/raw/other/sol/transactions').glob('*.json.gz'):
        envelope=load(path);payload=envelope.get('request',{}).get('json') or {}
        if payload.get('method')!='getTransaction':continue
        sig=payload['params'][0]
        result=envelope.get('response',{}).get('result')
        if sig in wanted and result is not None:
            transactions[sig]=(result,str(path.relative_to(ROOT))+'#/response/result')
    signature_meta=t['fetch_state']['signatures']
    ordered=sorted(transactions.items(),key=lambda item:(item[1][0]['slot'],signature_meta.get(item[0],{}).get('transactionIndex',0),item[0]))
    owners={};events=[];gaps=[];hints_used=0
    for sig,(tx,ref) in ordered:
        keys=[a['pubkey'] if isinstance(a,dict) else a for a in tx['transaction']['message']['accountKeys']]
        meta=tx['meta'];hints=dict(owners)
        instructions=[(i,f'{ref}/transaction/message/instructions/{j}') for j,i in enumerate(tx['transaction']['message'].get('instructions',[]))]
        for j,group in enumerate(meta.get('innerInstructions',[]) or []):
            instructions.extend((i,f'{ref}/meta/innerInstructions/{j}/instructions/{k}') for k,i in enumerate(group.get('instructions',[])))
        changes={};initialized={}
        if not meta.get('err'):
            for ins,ir in instructions:
                if ins.get('program') not in ('spl-token','spl-token-2022','spl-associated-token-account'):continue
                parsed=ins.get('parsed',{})
                if not isinstance(parsed,dict):continue
                info=parsed.get('info',{})
                kind=parsed.get('type')
                if kind in ('initializeAccount','initializeAccount2','initializeAccount3') and info.get('account') and info.get('owner'):
                    initialized[info['account']]=(info['owner'],ir)
                if ins.get('program')=='spl-associated-token-account' and kind in ('create','createIdempotent') and info.get('account') and info.get('wallet'):
                    initialized[info['account']]=(info['wallet'],ir)
                if kind=='setAuthority' and info.get('authorityType')=='accountOwner':
                    changes[info.get('account')]=(info.get('newAuthority'),ir)
        hints.update(initialized)
        for phase in ('preTokenBalances','postTokenBalances'):
            for i,b in enumerate(meta.get(phase,[]) or []):
                account=keys[b['accountIndex']]
                if b.get('owner') and (phase=='preTokenBalances' or account not in changes):
                    hints[account]=(b['owner'],f'{ref}/meta/{phase}/{i}/owner')
        # Metadata-free ownership changes cannot be projected across phases.
        for account in changes:hints.pop(account,None)
        parsed,owned=parser(tx,t['address'],ref,hints)
        events.extend(parsed)
        hints_used+=sum(bool(e.get('owner_resolution_raw_refs')) for e in parsed)
        for phase in ('preTokenBalances','postTokenBalances'):
            for i,b in enumerate(meta.get(phase,[]) or []):
                account=keys[b['accountIndex']]
                if not b.get('owner') and account not in hints:
                    # Only retain unresolved accounts associated with this wallet's
                    # signature streams; other transaction participants are out of scope.
                    if account in t['fetch_state']['signature_streams']:
                        gaps.append({'signature':sig,'token_account':account,'mint':b['mint'],
                                     'raw_ref':f'{ref}/meta/{phase}/{i}','reason':'No explicit prior/same-transaction owner proof'})
        owners.update(hints);owners.update(initialized);owners.update(changes)
        for i,b in enumerate(meta.get('postTokenBalances',[]) or []):
            if b.get('owner'):owners[keys[b['accountIndex']]]=(b['owner'],f'{ref}/meta/postTokenBalances/{i}/owner')
        for account in owned:
            t['fetch_state']['signature_streams'].setdefault(account,{'before':None,'complete':False,'pages':0})
    t['txs']=merge_txs(events)
    t['owner_resolution']={'method':'Chronological explicit token initialization/metadata/authority changes',
          'events_resolved_from_prior_evidence':hints_used,'unresolved_balance_records':gaps,
          'known_transactions_reparsed':len(transactions)}
    return t
