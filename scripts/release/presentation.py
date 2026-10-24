"""Public presentation fields derived from saved research, without changing results."""
import csv
csv.field_size_limit(100_000_000)
from collections import Counter
from statistics import median
from policy import load, dump


def enrich(root, dest):
    with (root/'data/ledger.csv').open(newline='') as handle:
        ledger=list(csv.DictReader(handle))
    by_id={}
    for row in ledger:
        by_id.setdefault(row['chain'].lower()+':'+row['address_normalized'],[]).append(row)
    index=load(dest/'site/data/addresses.json')
    for row in index:
        sources=by_id.get(row['id']) or [dict(chain_rule='explicit OFAC native-chain ticker (per-address inventory)', chain_confidence='high', ticker=row['ticker'])]
        row['chain_rules']=sorted({r['chain_rule'] for r in sources})
        row['chain_confidence']='medium' if any(r['chain_confidence']=='medium' for r in sources) else sources[0]['chain_confidence']
        row['source_tickers']=sorted({r['ticker'] for r in sources})
        row['source_ticker_mismatch']=any('override' in r['chain_rule'] for r in sources)
        row['chain_rule']='; '.join(row['chain_rules'])
        path=dest/'site/data/address'/row['chain']/(row['address']+'.json')
        detail=load(path)
        for key in ('chain_rule','chain_rules','chain_confidence','source_tickers','source_ticker_mismatch'):
            detail[key]=row[key]
        dump(path,detail)
    dump(dest/'site/data/addresses.json',index)
    freezes=load(dest/'site/data/freezes.json')
    summaries=load(root/'results/freeze_match.json')['summary']
    for row in freezes['summary']:
        source=next(s for s in summaries if s['issuer']==row['issuer'] and s['chain'].lower()==row['chain'] and s.get('program')=='ALL' and s.get('year')=='ALL' and s.get('variant')=='all')
        for key in ('blacklisted_current','unblacklisted_ever','valid_token_addresses'):
            row[key]=source[key]
    inferred={r['address_normalized'] for r in ledger if r['chain']=='ETH' and r['chain_confidence']=='medium'}
    with (root/'data/derived/freeze_match.csv').open(newline='') as handle:
        matched=list(csv.DictReader(handle))
    freezes['network_sensitivity']=[]
    for issuer in ('circle','tether'):
        rows=[r for r in matched if r['issuer']==issuer and r['chain']=='ETH' and r['listing_relation']=='OFAC-listed chain' and r['address'] not in inferred]
        first=[r for r in rows if r['blacklisted_ever']=='true']
        freezes['network_sensitivity'].append(dict(issuer=issuer,listed=len(rows),ever=len(first),current=sum(r['blacklisted_current']=='true' for r in rows),before_day=sum(float(r['lag_upper_hours'])<0 for r in first),median_hours=median(float(r['lag_hours']) for r in first),median_lower_hours=median(float(r['lag_lower_hours']) for r in first),median_upper_hours=median(float(r['lag_upper_hours']) for r in first),source_url='data/derived/freeze_match.csv.gz',raw_ref='data/freezes.csv;data/ledger.csv',excluded_addresses=sorted(inferred)))
    eth={r['address_normalized'] for r in ledger if r['chain']=='ETH'}
    with (root/'data/freezes.csv').open(newline='') as handle:
        dates=Counter(r['timestamp'][:10] for r in csv.DictReader(handle) if r['chain']=='ETH' and r['token']=='USDC' and r['event']=='UnBlacklisted' and r['address_normalized'] in eth)
    freezes['circle_removal_dates_utc']=dict(sorted(dates.items()))
    dump(dest/'site/data/freezes.json',freezes)
    graph=load(dest/'site/data/sankey.json')
    flow=load(root/'results/flows.json')
    graph['original_classes']=flow['summary']['classes']
    total=flow['summary']['wallet_outflows_usd']['value']
    unknown=next(c['usd']['value'] for c in graph['original_classes'] if c['class']=='unlabelled')
    graph['original_unlabelled_share']={'value':unknown/total,'unit':'share','source_url':'results/flows.json#summary.classes'}
    graph['presentation_grouping']={'unlabelled':['unlabelled','defi_other'],'cex_deposit':['cex_deposit','cex_hot']}
    for node in graph['nodes']:
        if node['id']=='class:unlabelled':node['label']='Other / unclassified'
        if node['id']=='class:cex_deposit':node['label']='Exchange-labelled address'
    dump(dest/'site/data/sankey.json',graph)
