"""Audit AccountRoot continuity and repair missing intervals using bounded RPCs.

Cross-provider account_tx markers are not portable. Every detected gap is
refetched independently by ledger interval without borrowing another marker.
"""
import json
import argparse
from pathlib import Path
from fetch import rpc,XRP_SERVERS,parse_xrp
from common import Client,ROOT,load,save,merge_txs,set_bounds,timeline_path,now

def roots(t):
    rows={};raw_cache={}
    for e in t['txs']:
        p,pointer=e['raw_ref'].split('#')
        if p not in raw_cache:raw_cache[p]=load(ROOT/p)
        entry=raw_cache[p]
        for key in pointer.strip('/').split('/'):
            entry=entry[int(key)] if isinstance(entry,list) else entry[key]
        tx=entry.get('tx',entry.get('tx_json',{}))
        for node in entry['meta'].get('AffectedNodes',[]):
            action,n=next(iter(node.items()));f=n.get('FinalFields',n.get('NewFields',{}));prev=n.get('PreviousFields',{})
            if n.get('LedgerEntryType')!='AccountRoot' or f.get('Account')!=t['address']:continue
            final=int(f.get('Balance',0));initial=int(prev.get('Balance',final))
            if action=='CreatedNode':initial=0
            if action=='DeletedNode':final=0
            rows[e['hash']]={'ledger':tx.get('ledger_index',e['block']), 'index':entry['meta']['TransactionIndex'],
                  'before':initial,'after':final,'hash':e['hash'],'raw_ref':e['raw_ref']}
    return sorted(rows.values(),key=lambda r:(r['ledger'],r['index']))

def gaps(t):
    last=0;last_ledger=0;result=[]
    for row in roots(t):
        if row['before']!=last:
            result.append({'from_ledger':last_ledger,'to_ledger':row['ledger'],
                           'previous_balance':last,'next_before_balance':row['before'],'next_raw_ref':row['raw_ref']})
        last=row['after'];last_ledger=row['ledger']
    return result,last

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',default='data/raw/other/xrp/continuity-audit.json.gz')
    parser.add_argument('--offline',action='store_true',help='Audit saved evidence without repairing gaps')
    args=parser.parse_args()
    c=Client(source='other',delay=2,retries=2)
    reports=[]
    for p in (ROOT/'data/timelines/xrp').glob('*.json.gz'):
        t=load(p);original,final=gaps(t);rep={'address':t['address'],'before_gaps':original,'repair_responses':[]}
        for gap in ([] if args.offline else original):
            marker=None;server=XRP_SERVERS[0]
            while True:
                params={'account':t['address'],'ledger_index_min':gap['from_ledger'],
                        'ledger_index_max':gap['to_ledger'],'limit':200,'forward':True,'binary':False}
                if marker:params['marker']=marker
                result,r=rpc(c,[server],'account_tx',params,'xrp/repair',xrp=True)
                rep['repair_responses'].append(r)
                for i,entry in enumerate(result.get('transactions',[])):
                    t['txs'].extend(parse_xrp(entry,t['address'],f'{r}#/response/result/transactions/{i}'))
                marker=result.get('marker')
                if not marker:break
        t['txs']=merge_txs(t['txs']);remaining,final=gaps(t)
        rep.update(after_gaps=remaining,last_history_balance_drops=str(final))
        t['coverage']['account_root_continuity_complete']=not remaining
        t['coverage']['complete']=t['fetch_state']['complete'] and not remaining
        note='AccountRoot before/after balances audited in ledger/transaction order. Cross-provider marker boundary gaps were repaired using bounded ledger requests; see data/raw/other/xrp/continuity-audit.json.gz.'
        if note not in t['coverage']['notes']:t['coverage']['notes'].append(note)
        t['fetch_state']['server']=XRP_SERVERS[0]
        set_bounds(t);save(p,t);reports.append(rep)
    save(ROOT/args.report,{'checked_at':now(),'reports':reports,'offline':args.offline})
    print(json.dumps(reports))

if __name__=='__main__':main()
