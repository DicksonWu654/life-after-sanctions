#!/usr/bin/env python3
"""Evidence-linked, provisional first-hop flow analysis. Standard library only.

Default: snapshot whatever complete JSON timeline files exist and rebuild outputs.
--resume: rebuild from the last immutable input snapshot (also after trace.py).
--check: offline reproduction of the published snapshot, CSV, JSON and report.
--self-test: meaningful transaction-semantics regression checks, no output writes.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import sqlite3
import sys
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.labels.lookup import label
from scripts.labels.policy import normalize_address, normalize_chain, EVM
from scripts.prices import price

RAW = ROOT / 'data/raw/flows'
RESULT = ROOT / 'results/flows.json'
EDGES = ROOT / 'data/derived/flows_edges.csv'
DOC = ROOT / 'docs/analysis/FLOWS.md'
UTC = dt.timezone.utc
ET = ZoneInfo('America/New_York')
CLASSES = ('mixer', 'bridge', 'dex', 'cex_deposit', 'cex_hot',
           'other_sanctioned', 'issuer', 'defi_other', 'unlabelled')
SITE_CLASSES = ('mixer', 'bridge', 'dex', 'cex_deposit', 'other_sanctioned', 'unlabelled')
NATIVE = {c:c for c in ('BTC','LTC','BCH','BSV','DASH','DOGE','ZEC','XVG','XRP','SOL','TRX','ETC','BNB')}
NATIVE.update(ETH='ETH', ARB='ETH', BASE='ETH', OP='ETH', BSC='BNB', POLYGON='MATIC/POL', AVAX='AVAX')
# Identity comes from exact contracts, never a token's self-reported symbol.
# Stablecoin contracts agree with the reviewed acquisition registry; DAI/WETH
# addresses are independently explicit token-contract labels in labels.csv.
TOKENS = {
 'ETH': {'0xdac17f958d2ee523a2206206994597c13d831ec7':('USDT',6),
         '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48':('USDC',6),
         '0x6b175474e89094c44da98b954eedeac495271d0f':('DAI',18)},
 'TRX': {'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':('USDT',6)},
 'ARB': {'0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9':('USDT',6),
         '0xaf88d065e77c8cc2239327c5edb3a432268e5831':('USDC',6)},
 'BASE': {'0x833589fcd6edb6e08f4c7c32d4f71b54bda02913':('USDC',6)},
 'OP': {'0x0b2c639c533813f4aa9d7837caf62653d097ff85':('USDC',6),
        '0x94b008aa00579c1307b0ef2c499ad98a8ce58e58':('USDT',6)},
 'POLYGON': {'0xc2132d05d31c914a87c6611c10748aeb04b58e8f':('USDT',6),
             '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359':('USDC',6)},
}
HOP_RULE = ('First receipt is hop 1. Process selected first-hop receipts FIFO by time/block/hash. '
            'At each unlabelled address select its earliest later outgoing transaction of the same exact asset; '
            'if that transaction has multiple outputs follow its largest output (ties: destination then event id). '
            'Reserve that outgoing transaction once across FIFO paths; do not substitute its smaller outputs, split or proportionally haircut lots. '
            'Stop at the first labelled class, unresolved ordering/coverage, repeated address, or hop 5. '
            'This is a temporal path heuristic, not a balance-aware FIFO taint accounting system: earlier unrelated '
            'balances, mixing and ownership are unknown. Original USD is a seed-weight only; no downstream USD attribution.')


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rel(path):
    return str(path.relative_to(ROOT))


def load(path):
    with (gzip.open(path, 'rt') if str(path).endswith('.gz') else path.open()) as f:
        return json.load(f)


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.flows.tmp')
    tmp.write_bytes(data)
    tmp.replace(path)


def archive(obj, category):
    body = canonical(obj)
    path = RAW / category / (sha(body) + '.json.gz')
    if not path.exists():
        atomic(path, gzip.compress(body, mtime=0))
    return rel(path)


def number(value, unit, valued_at=None):
    out = {'value':round(float(value), 6) if unit in ('usd','share') else value, 'unit':unit}
    if unit == 'usd': out['valued_at'] = valued_at or 'at transfer time'
    return out


def dec(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else Decimal(0)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)


def timestamp(value):
    if not value: return None
    try:
        return dt.datetime.fromisoformat(str(value).replace('Z','+00:00')).replace(tzinfo=UTC) if len(str(value)) == 10 else dt.datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(UTC)
    except (ValueError, TypeError): return None


def designation(value):
    if not value: return None
    if len(value) == 10:
        return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), ET).astimezone(UTC)
    return timestamp(value)


def explorer(chain, txhash):
    bases = {'ETH':'https://etherscan.io/tx/', 'TRX':'https://tronscan.org/#/transaction/',
             'BTC':'https://mempool.space/tx/', 'LTC':'https://litecoinspace.org/tx/',
             'BSC':'https://bscscan.com/tx/', 'ARB':'https://arbiscan.io/tx/',
             'BASE':'https://basescan.org/tx/', 'OP':'https://optimistic.etherscan.io/tx/',
             'POLYGON':'https://polygonscan.com/tx/', 'ETC':'https://etc.blockscout.com/tx/',
             'SOL':'https://solscan.io/tx/', 'XRP':'https://livenet.xrpl.org/transactions/'}
    if chain in bases: return bases[chain] + str(txhash)
    return 'https://blockchair.com/' + {'BCH':'bitcoin-cash','BSV':'bitcoin-sv','DOGE':'dogecoin','DASH':'dash','ZEC':'zcash'}.get(chain, chain.lower()) + '/transaction/' + str(txhash)


@lru_cache(maxsize=200000)
def claims(chain, address):
    if not address or address.startswith('__') or (chain,address) not in label_keys():return []
    return label(chain,address)


@lru_cache(maxsize=1)
def label_keys():
    """Avoid opening SQLite once per unknown pool counterparty; exact lookup
    still supplies every matched claim, conflict and evidence field.
    """
    from scripts.labels.lookup import DATABASE
    if not DATABASE.is_file():raise FileNotFoundError(DATABASE)
    with sqlite3.connect(DATABASE.as_uri()+'?mode=ro',uri=True) as connection:
        return set(connection.execute('SELECT DISTINCT chain,address_normalized FROM labels'))


def classify(chain, address, when, index):
    rows = claims(chain,address)
    applicable = []
    for row in rows:
        if row['class'] not in CLASSES: continue
        if row['class'] == 'other_sanctioned':
            start, end = designation(row.get('valid_from')), designation(row.get('valid_to'))
            if not start or when < start or (end and when >= end): continue
        applicable.append(row)
    # Independent functional service classification precedes OFAC membership.
    roles = sorted({r['class'] for r in applicable if r['class'] != 'other_sanctioned'})
    if len(roles) > 1:
        return 'unlabelled', '', rows, 'conflicting functional classes: ' + ';'.join(roles)
    chosen = roles[0] if roles else ('other_sanctioned' if applicable else 'unlabelled')
    picked = [r for r in applicable if r['class'] == chosen]
    names = '; '.join(sorted({r['label'] for r in picked}))
    return chosen, names, rows, ('service label historical validity unverified' if roles else 'as-of-transfer OFAC membership' if applicable else 'no applicable role label')


def token_asset(chain, tx):
    asset = str(tx.get('asset') or '')
    normal = normalize_address(chain,asset)
    native = NATIVE.get(chain)
    if native and asset.upper() in {native, 'POL', 'MATIC'} and not asset.startswith(('0x','trc10:')):
        if native == 'MATIC/POL' or asset.upper() == native:
            return native, 'native asset; chain identity'
    token = TOKENS.get(chain,{}).get(normal)
    if token and tx.get('decimals') is not None and int(tx['decimals']) == token[1] and not tx.get('amount_is_raw_units'):
        return token[0], 'exact contract + decimals allowlist'
    return None, 'unknown contract, unsupported asset, or unresolved decimals; symbol never trusted'


def split_transfer(chain, address, tx):
    """(destination, amount, semantics, count_in_total, output_index) rows."""
    value = dec(tx.get('amount'))
    if value <= 0 or tx.get('success') is False or tx.get('is_transfer') is False: return []
    if tx.get('status') in ('FAILED','failed','error'): return []
    if 'outputs' in tx:
        if not tx.get('block'): return []
        inputs = tx.get('inputs',[])
        owned = sum(int(v.get('value_sat',0)) for v in inputs if address in v.get('addresses',[]))
        if owned <= 0: return []
        exact = all(v.get('addresses') == [address] for v in inputs)
        result = []
        for i, out in enumerate(tx['outputs']):
            addrs = out.get('addresses',[])
            if addrs == [address]: continue
            dest = addrs[0] if len(addrs) == 1 else '__undecodable_utxo_output__'
            amount = Decimal(int(out.get('value_sat',0))) / Decimal(10**8)
            if amount:
                result.append((dest,amount,'single-source UTXO output' if exact else 'mixed-input candidate output; source contribution unallocated',exact,i))
        if not exact and tx.get('direction') == 'out':
            result.append(('__mixed_input_utxo__', value, 'net debit excluding allocated fee; destination unallocated',True,-1))
        return result
    if tx.get('direction') not in ('out','self'): return []
    if tx.get('counterparty_amounts'):
        return [(v['address'],dec(v['amount']),'pool beneficiary/relayer decoded from event',True,i) for i,v in enumerate(tx['counterparty_amounts']) if dec(v['amount']) > 0]
    dest = tx.get('to')
    if not dest:
        parties = tx.get('counterparties',[])
        # XRPL AccountRoot changes do not identify the economic recipient.
        if chain != 'XRP' and len(parties) == 1: dest = parties[0]
        else: dest = '__unresolved_destination__'
    return [(dest,value,'direct transfer' if not dest.startswith('__') else 'balance debit; recipient unallocated',True,0)]


def snapshot():
    addresses = list(csv.DictReader((ROOT/'data/addresses.csv').open()))
    ledger = list(csv.DictReader((ROOT/'data/ledger.csv').open()))
    rows, manifest, coverage = [], [], []
    counts = collections.Counter()
    for entry in sorted(addresses, key=lambda r:(r['chain'],r['address_normalized'])):
        chain = normalize_chain(entry['chain']); addr = normalize_address(chain, entry['address_normalized'])
        t = designation(entry.get('first_listed_date'))
        choices = [ROOT/'data/timelines'/chain.lower()/(addr+suffix) for suffix in ('.json.gz','.json')]
        path = next((p for p in choices if p.is_file()), None)
        stat = {'chain':chain,'address':addr,'trackable':entry.get('trackable') == 'true','first_listed_date':entry.get('first_listed_date'),
                'timeline':rel(path) if path else None, 'complete':False,'transactions':0,'status':'missing'}
        if not path:
            counts['missing'] += 1; coverage.append(stat); continue
        counts['files_present'] += 1
        try:
            body = path.read_bytes()
            d = json.loads(gzip.decompress(body) if path.suffix == '.gz' else body)
            if not isinstance(d,dict) or not isinstance(d.get('txs'),list): raise ValueError('missing txs array')
            if normalize_chain(d.get('chain','')) != chain or normalize_address(chain,d.get('address','')) != addr: raise ValueError('timeline identity mismatch')
        except (OSError, ValueError, EOFError, TypeError) as exc:
            stat.update(status='unreadable', error=str(exc)[:200]); coverage.append(stat); counts['unreadable'] += 1; continue
        stat.update(status='readable', complete=bool(d.get('coverage',{}).get('complete')),transactions=len(d['txs']),
                    fetched_at=d.get('fetched_at'), to_time=d.get('coverage',{}).get('checked_through_time',d.get('coverage',{}).get('to_time')),
                    coverage_notes=d.get('coverage',{}).get('notes',[]), gaps=d.get('coverage',{}).get('missing_ranges',[]))
        stat['exchange_scale'] = len({tx.get('hash') for tx in d['txs']}) > 10000
        stat['tornado_contract'] = any('tornado' in r.get('label','').lower() and r['class'] == 'mixer' for r in claims(chain,addr))
        manifest.append({'path':rel(path),'sha256':sha(body),'fetched_at':d.get('fetched_at')})
        counts['readable'] += 1; counts['complete'] += stat['complete']
        if not t:
            stat['status']='unknown_designation'; counts['unknown_designation'] += 1
        for i, tx in enumerate(d['txs']):
            if tx.get('direction') not in ('out','self') and 'inputs' not in tx: continue
            if dec(tx.get('amount')) <= 0: continue
            when = timestamp(tx.get('time_utc'))
            if not when:
                counts['outgoing_missing_exact_time'] += 1; continue
            if not t or when < t: continue
            rows.append({'chain':chain,'source':addr,'timeline':rel(path),'timeline_index':i,
                         'tx':tx,'tornado_contract':stat['tornado_contract'],'exchange_scale':stat['exchange_scale']})
        coverage.append(stat)
        if counts['readable'] % 50 == 0:
            print(json.dumps({'stage':'snapshot','readable_timelines':counts['readable'],'candidate_outgoing_rows':len(rows)}),flush=True)
    partial = sorted(rel(p) for p in (ROOT/'data/timelines').glob('*/*') if '.tmp' in p.name or '.part' in p.name)
    return {'schema_version':1,'snapshot_at':dt.datetime.now(UTC).isoformat(),'addresses':addresses,'ledger':ledger,
            'manifest':manifest,'coverage':coverage,'read_counts':dict(counts),'ignored_partial_files':partial,'rows':rows,
            'shared_hashes':{str(p):sha((ROOT/p).read_bytes()) for p in ['data/labels/labels.csv','data/labels/labels.sqlite','scripts/prices/price.py','scripts/labels/policy.py','scripts/labels/lookup.py']},
            'price_hashes':{rel(p):sha(p.read_bytes()) for p in sorted((ROOT/'data/prices').glob('*.csv.gz'))}}


def index_addresses(snap):
    return {(normalize_chain(r['chain']),normalize_address(normalize_chain(r['chain']),r['address_normalized'])):r for r in snap['addresses']}


def build_edges(snap):
    index = index_addresses(snap)
    result=[]; seen=set(); rejects=collections.Counter()
    for row in snap['rows']:
        tx=row['tx']; chain=row['chain']; address=row['source']; when=timestamp(tx['time_utc'])
        for dest,amount,semantics,included,output_index in split_transfer(chain,address,tx):
            dest=normalize_address(chain,dest)
            event=str(tx.get('event_id') or tx.get('logIndex') or tx.get('traceId') or '')
            # Preserve repeated logs lacking indexes using original timeline position.
            ident=(chain,address,str(tx.get('hash')),str(tx.get('asset')),tx.get('kind',''),event or row['timeline_index'],output_index)
            if ident in seen: rejects['duplicate_rows']+=1; continue
            seen.add(ident)
            asset,identity=token_asset(chain,tx)
            unit_price,observed,source=(price.usd(asset,when) if asset else (None,None,None))
            usd=amount * Decimal(str(unit_price)) if unit_price is not None else None
            cls,name,labels,reason=classify(chain,dest,when,index)
            src=index[(chain,address)]; dest_entry=index.get((chain,dest))
            # Same-entity means shared OFAC UID and both strings designated by this transfer date.
            shared=sorted(set(src.get('sdn_uids',src.get('all_entity_uids','')).split(';')) & set((dest_entry or {}).get('sdn_uids',(dest_entry or {}).get('all_entity_uids','')).split(';')) - {''})
            dest_t=designation((dest_entry or {}).get('first_listed_date'))
            dest_end=designation((dest_entry or {}).get('delisted_date'))
            self_entity=bool(shared and dest_t and when >= dest_t and (not dest_end or when < dest_end))
            if self_entity:
                if cls=='unlabelled':cls='other_sanctioned'
                reason += '; same OFAC entity UID'
            if usd is None: rejects['unpriced_edges']+=1
            price_row=None
            if asset and observed:
                for frequency in ('1h','1d'):
                    r=price._lookup_rows(asset,frequency,when)
                    if r and r['valuation_time_utc']==observed and r['source']==source: price_row=r;break
            result.append({'edge_id':sha(canonical(ident))[:24], 'chain':chain,'source_address':address,'destination_address':dest,
                 'designation_date':src.get('first_listed_date'),'programs':src.get('programs',''), 'source_entity_uids':src.get('sdn_uids',src.get('all_entity_uids','')),
                 'hash':tx.get('hash'),'time_utc':tx['time_utc'],'block':tx.get('block'),'event_id':event,
                 'asset':tx.get('asset'),'price_asset':asset or '', 'amount_native':str(amount),
                 'usd':str(usd) if usd is not None else '', 'price_usd':str(unit_price) if unit_price is not None else '',
                 'valued_at':observed or '', 'price_source':source or '', 'price_raw_ref':(price_row or {}).get('raw_ref',''),
                 'destination_class':cls,'destination_label':name,'label_reason':reason,
                 'label_claims':json.dumps(labels,sort_keys=True,separators=(',',':')), 'self_transfer_same_entity':self_entity,
                 'shared_entity_uids':';'.join(shared),'self_transfer_same_address':dest==address,
                 'is_dust':bool(usd is not None and usd < 1), 'included_in_total':included,
                 'tornado_contract':row['tornado_contract'],'exchange_scale':row['exchange_scale'],
                 'semantics':semantics,'asset_identity_rule':identity,'timeline_ref':row['timeline']+'#/txs/'+str(row['timeline_index']),
                 'source_url':explorer(chain,tx.get('hash')), 'raw_ref':tx.get('raw_ref','')})
    return sorted(result,key=lambda r:(r['chain'],r['source_address'],r['time_utc'],str(r['hash']),r['edge_id'])),dict(rejects)


def eligible(e):
    return bool(e['included_in_total'] and e['usd'] and not e['is_dust'] and not e['tornado_contract'] and not e['self_transfer_same_address'])


def total(edges): return sum((dec(e['usd']) for e in edges),Decimal(0))


def sankey(edges, dimension):
    links=collections.defaultdict(Decimal)
    for e in edges:
        cls={'cex_hot':'cex_deposit','issuer':'unlabelled','defi_other':'unlabelled'}.get(e['destination_class'],e['destination_class'])
        sources=[e['chain']] if dimension=='chain' else sorted(set(filter(None,e['programs'].split(';')))) or ['UNSPECIFIED']
        for s in sources: links[(s,cls)] += dec(e['usd']) / len(sources)
    nodes=[{'id':dimension+':'+s,'label':s,'kind':dimension} for s in sorted({a for a,b in links})]
    nodes += [{'id':'class:'+c,'label':c,'kind':'destination_class'} for c in SITE_CLASSES]
    return {'unit':'usd','valued_at':'at transfer time','nodes':nodes,
            'links':[{'source':dimension+':'+s,'target':'class:'+c,'value':round(float(v),6)} for (s,c),v in sorted(links.items())],
            'hop_rule':HOP_RULE,'notes':['First-hop only. Alternative program and chain views describe the same gross dollars; never add them.',
                'Shared-program rows split equally across distinct tags, preserving total; this is an accounting convention.',
                'cex_hot folds into cex_deposit; issuer/defi_other into unlabelled solely for site taxonomy. Full classes remain in detailed data.',
                'Excludes Tornado source contracts, self-address transfers and priced transfers below USD 1; includes within-entity transfers separately flagged.',
                'Mixed-input UTXO net debits remain unallocated/unlabelled; candidate outputs are evidence only. No still_there/frozen stock is added to gross flows.']}


def examples(edges,n=3):
    out=[]; seen=set()
    for e in sorted(edges,key=lambda e:dec(e['usd']),reverse=True):
        if e['hash'] in seen: continue
        seen.add(e['hash']); out.append({k:e[k] for k in ('chain','hash','source_url','raw_ref','time_utc','valued_at','source_address','destination_address','destination_label')})
        if len(out)==n: break
    return out


def select_seeds(edges,target=0.8,cap=400):
    groups=collections.defaultdict(list)
    for e in edges:
        if e['destination_class']=='unlabelled' and not e['destination_address'].startswith('__'):
            groups[(e['chain'],e['destination_address'])].append(e)
    ordered=sorted(groups,key=lambda k:(-total(groups[k]),k))
    denominator=total([e for e in edges if e['destination_class']=='unlabelled'])
    chosen=[]; running=Decimal(0)
    for key in ordered:
        if len(chosen)>=cap or (running>=denominator*Decimal(str(target)) and chosen): break
        value=total(groups[key]); running+=value
        chosen.append({'chain':key[0],'address':key[1],'usd':number(value,'usd'),
                       'edges':[e['edge_id'] for e in sorted(groups[key],key=lambda e:(e['time_utc'],str(e.get('block')),e['hash'],e['edge_id']))]})
    return {'target':number(target,'share'),'cap':number(cap,'addresses'),'selected_count':number(len(chosen),'addresses'),
            'unlabelled_usd':number(denominator,'usd'),'selected_usd':number(running,'usd'),
            'achieved_share':number(running/denominator if denominator else 0,'share'),
            'target_met':bool(not denominator or running>=denominator*Decimal(str(target))), 'seeds':chosen}


def build_result(snap,snapshot_ref,edges,rejects,trace_bundle=None):
    core=[e for e in edges if eligible(e)]; cov=snap['coverage']; seed=select_seeds(core)
    classes=collections.defaultdict(list)
    for e in core: classes[e['destination_class']].append(e)
    per_chain=[]
    for chain in sorted({r['chain'] for r in cov}):
        rows=[r for r in cov if r['chain']==chain]; es=[e for e in core if e['chain']==chain]
        per_chain.append({'chain':chain,'ledger_addresses':number(len(rows),'addresses'),
            'timelines_readable':number(sum(r['status'] in ('readable','unknown_designation') for r in rows),'addresses'),
            'complete_histories':number(sum(r['complete'] for r in rows),'addresses'),
            'missing':number(sum(r['status']=='missing' for r in rows),'addresses'),
            'unreadable':number(sum(r['status']=='unreadable' for r in rows),'addresses'),
            'untrackable':number(sum(not r['trackable'] for r in rows),'addresses'),
            'outflows':number(len(es),'events'),'outflow_usd':number(total(es),'usd')})
    named=collections.defaultdict(list)
    for e in core:
        if e['destination_label']: named[(e['chain'],e['destination_address'],e['destination_class'],e['destination_label'])].append(e)
    top=[{'chain':k[0],'address':k[1],'class':k[2],'label':k[3], 'usd':number(total(v),'usd'),'events':number(len(v),'events'),
          'label_claims':json.loads(v[0]['label_claims']),'examples':examples(v)} for k,v in sorted(named.items(),key=lambda kv:(-total(kv[1]),kv[0]))[:30]]
    finding=[]
    uid_names={row['sdn_uid']:row['sdn_name'] for row in snap['ledger']}
    entity_edges=collections.defaultdict(list)
    for e in core:
        for uid in set(filter(None,e['source_entity_uids'].split(';'))):entity_edges[uid].append(e)
    source_entities=[{'uid':uid,'name':uid_names.get(uid,uid),'usd':number(total(es),'usd'),
                     'addresses':number(len({(e['chain'],e['source_address']) for e in es}),'addresses'),
                     'events':number(len(es),'events'),'examples':examples(es)}
                    for uid,es in sorted(entity_edges.items(),key=lambda kv:(-total(kv[1]),kv[0]))[:20]]
    chen=[e for e in core if any(uid_names.get(uid)=='CHEN, Zhi' for uid in e['source_entity_uids'].split(';'))]
    if len({e['hash'] for e in chen})>=2:
        finding.append({'id':'flows-chen-seizure-confounder',
            'sentence':f"Addresses OFAC lists under CHEN, Zhi sent {float(total(chen)):,.2f} USD after their identifier designation, including {sum(e['chain']=='BTC' and e['time_utc'].startswith('2025-10-22') for e in chen)} Bitcoin output edges on 2025-10-22; destination labels are limited by the public label set.",
            'amount':number(total(chen),'usd'),'events':number(len(chen),'events'),'examples':examples(chen),
            'confidence':'High confidence in amounts and OFAC source-address membership, provisional coverage. Do not describe this as evasion: the saved TRM account of the 2025-10-14 action reports a contemporaneous DOJ forfeiture and government custody. That context does not establish the owner of these particular recipient addresses.',
            'context_sources':[{'source_url':'https://www.trmlabs.com/resources/blog/historic-u-s--u-k-operation-targets-southeast-asias-scam-compounds-with-record-15-billion-bitcoin-seizure',
                                'raw_ref':'data/raw/priorart/pages/trm-prince.txt.gz'}]})
    if total(core) and len({e['hash'] for e in classes['unlabelled']})>=2:
        unknown_share=total(classes['unlabelled'])/total(core)
        finding.append({'id':'flows-unlabelled-first-hop',
            'sentence':f"{float(unknown_share):.2%} of observed wallet outflow USD at transfer time has an unlabelled first-hop role in the saved public label set.",
            'amount':number(unknown_share,'share'),'denominator':number(total(core),'usd'),
            'examples':examples(classes['unlabelled']),
            'confidence':'High confidence as a description of this dataset, not of actual service use. Generic exchange tags, unresolved output attribution and scarce BTC/Tron service labels remain unlabelled. A zero first-hop mixer/CEX count is not evidence that no mixer/CEX was reached later.'})
    for cls in ('mixer','bridge','dex','other_sanctioned'):
        es=classes[cls]
        if total(es)>=10000 and len({e['hash'] for e in es})>=2:
            finding.append({'id':'flows-direct-'+cls,'sentence':f'Listed source wallets sent {float(total(es)):,.2f} USD directly to destinations classified {cls}, within the timelines checked.',
                'amount':number(total(es),'usd'),'events':number(len(es),'events'), 'examples':examples(es),
                'confidence':'Provisional. Transfer amounts have raw evidence; public service labels are leads, often without historical validity. Gross transfers can recirculate; amounts are not unique funds or proof of unlawful conduct.'})
    selfes=[e for e in core if e['self_transfer_same_entity']]
    if len({e['hash'] for e in selfes})>=2:
        finding.insert(0,{'id':'flows-within-entity','sentence':f'{float(total(selfes)):,.2f} USD of observed gross outflows moved between addresses sharing an OFAC entity UID.',
            'amount':number(total(selfes),'usd'),'events':number(len(selfes),'events'),'examples':examples(selfes),
            'confidence':'High confidence in shared OFAC UID; both addresses were listed by transfer time. This is a gross internal movement measure, not additional money leaving the entity. Provisional timeline coverage.'})
    paths=(trace_bundle or {}).get('paths',[])
    mixer_paths=[p for p in paths if p.get('terminal_class')=='mixer' and p['status']=='label_reached']
    if len(mixer_paths)>=2:
        terminal_examples=[]
        for path in mixer_paths[:3]:
            last=path['steps'][-1]
            _,observed,_=price.usd(NATIVE.get(path['chain'],path['chain']),last['time_utc'])
            terminal_examples.append({'chain':path['chain'],'hash':last['hash'],'source_url':last['source_url'],
                  'raw_ref':last['raw_ref'],'time_utc':last['time_utc'],'valued_at':observed,
                  'source_address':last['from'],'destination_address':last['to'],'destination_label':path.get('terminal_label','')})
        finding.insert(0,{'id':'flows-mixer-paths',
            'sentence':f"{len(mixer_paths)} selected first-hop receipt paths reached a mixer-labelled destination at hop counts {', '.join(map(str,sorted({p['hops'] for p in mixer_paths})))}, counting the listed-address transfer as hop 1.",
            'amount':number(len(mixer_paths),'events'),'examples':terminal_examples,
            'confidence':'Observed same-asset temporal paths under the FIFO/largest-output rule; public protocol labels have raw sources. This does not attribute the full seed amount to the terminal transfer. Dates in the examples are essential: a mixer role does not mean the service was designated at that time; Tornado Cash was first designated on 2022-08-08.'})
    hops=[]
    for cls in ('mixer','cex_deposit','cex_hot'):
        for hop in range(1,6):
            direct=[e for e in core if e['destination_class']==cls] if hop==1 else []
            ps=[p for p in paths if p.get('terminal_class')==cls and p.get('hops')==hop and p['status']=='label_reached'] if hop>1 else []
            hops.append({'class':cls,'hops':hop,'paths':number(len(direct)+len(ps),'events'),
                         'seed_weight_usd':number(total(direct)+sum((dec(p['seed_usd']) for p in ps),Decimal(0)),'usd'),
                         'meaning':'Original first-hop USD weight, not downstream value received or uniquely attributed funds.'})
    return {'schema_version':1,'provisional':True,'snapshot_at':snap['snapshot_at'],'snapshot_ref':snapshot_ref,
      'unit':'usd','valued_at':'at transfer time', 'timeline_count':number(snap['read_counts'].get('readable',0),'addresses'),
      'coverage':{'ledger_addresses':number(len(snap['addresses']),'addresses'),'per_chain':per_chain,
                  'unreadable_files':number(snap['read_counts'].get('unreadable',0),'events'),
                  'partial_files_ignored':number(len(snap['ignored_partial_files']),'events'),
                  'outgoing_rows_missing_exact_time':number(snap['read_counts'].get('outgoing_missing_exact_time',0),'events'),
                  'detail_ref':snapshot_ref+'#/coverage'},
      'summary':{'wallet_outflows_usd':number(total(core),'usd'),'wallet_outflow_events':number(len(core),'events'),
          'source_addresses_with_outflow':number(len({(e['chain'],e['source_address']) for e in core}),'addresses'),
          'without_exchange_scale_usd':number(total([e for e in core if not e['exchange_scale']]),'usd'),
          'within_entity_usd':number(total(selfes),'usd'),
          'tornado_source_contract_outflows_usd_separate':number(total([e for e in edges if e['tornado_contract'] and e['included_in_total']]),'usd'),
          'dust_usd_separate':number(total([e for e in edges if e['is_dust'] and e['included_in_total']]),'usd'),
          'unpriced_edges':number(rejects.get('unpriced_edges',0),'events'),
          'unallocated_destination_usd':number(total([e for e in core if e['destination_address'].startswith('__')]),'usd'),
          'classes':[{'class':c,'usd':number(total(classes[c]),'usd'),'events':number(len(classes[c]),'events')} for c in CLASSES]},
      'sankey':{'program':sankey(core,'program'),'chain':sankey(core,'chain')},
      'trace_selection':seed, 'trace':{'hop_rule':HOP_RULE,'bundle_ref':(trace_bundle or {}).get('bundle_ref'),
          'seed_addresses_attempted':number(len({(p['chain'],p['seed_address']) for p in paths}),'addresses'),
          'paths':number(len(paths),'events'),'outcomes':dict(collections.Counter(p['status'] for p in paths)),
          'hop_distribution_to_first_mixer_cex':hops,'notes':(trace_bundle or {}).get('notes',['No multi-hop requests yet. Run trace.py --fetch, then flows.py --resume.'])},
      'top_named_destinations':top,'top_source_entities':source_entities,
      'entity_aggregation_note':'Entity rows overlap if an address has multiple UIDs; do not sum rows. Address totals and Sankey count each source edge once.',
      'findings':finding,
      'evidence':{'edge_csv':rel(EDGES),'script':'scripts/analysis/flows.py','trace_script':'scripts/analysis/trace.py',
                  'raw_cache':'data/raw/flows/','snapshot_sha256':sha(canonical(snap))},
      'notes':['All results are provisional while fetchers run. Counts are chain-address pairs in the ledger, not entities.',
          'T is the start of the OFAC publication date in America/New_York; same-day order relative to publication is unknown.',
          'First-listed dates define the requested post-T window; later delisting does not truncate it. Post-delisting activity is not described as activity while sanctioned.',
          'Only ledger-listed chain-address pairs enter; same address on other chains is excluded.',
          'Service role conflicts, generic service labels and third-party risk-only labels map to unlabelled. Temporal OFAC membership is checked separately.',
          'Same-entity transfers stay in gross totals with an explicit flag; flows are not unique dollars or stock at designation.',
          'Research, not legal or compliance advice. Receipt from a sanctioned address does not establish knowledge, control or a legal violation. Exchanges may have frozen or reported funds.']}


def render_csv(edges):
    s=io.StringIO(newline=''); fields=list(edges[0]) if edges else ['edge_id','source_url','raw_ref']
    writer=csv.DictWriter(s,fieldnames=fields,lineterminator='\n'); writer.writeheader();writer.writerows(edges)
    return s.getvalue().encode()


def render_doc(r):
    s=r['summary']; sel=r['trace_selection']; lines=[
      '# Post-designation outflows — provisional', '',
      f"Snapshot: **{r['snapshot_at']}**. **{r['timeline_count']['value']:,} of {r['coverage']['ledger_addresses']['value']:,} ledger chain-address pairs** had readable timelines. {('Fetchers are still running.' if r.get('provisional', True) else 'Data as of ' + r['snapshot_at'][:10] + '; bounded acquisition is complete and source-specific history gaps remain.')} Every conclusion below means **within data checked**.", '',
      f"Observed wallet gross outflows: **${s['wallet_outflows_usd']['value']:,.2f} USD at transfer time**, across **{s['wallet_outflow_events']['value']:,} transfer/net-debit edges** from **{s['source_addresses_with_outflow']['value']:,} chain-address pairs**. This is gross turnover, not unique funds or value at designation.", '',
      '## Reproduce', '', '```sh', '.venv/bin/python scripts/analysis/flows.py', '.venv/bin/python scripts/analysis/trace.py --fetch', '.venv/bin/python scripts/analysis/flows.py --resume', '.venv/bin/python scripts/analysis/flows.py --check', '.venv/bin/python scripts/analysis/flows.py --self-test', '```', '',
      'Default scans current inputs; `--resume` and `--check` use the immutable published snapshot so concurrent timeline refreshes cannot silently change its cohort. `--check` reruns edge construction, classification, prices, selection, aggregation and Markdown/CSV generation; it rejects changed shared label/price dependencies and mismatched outputs. A fresh default run adopts newer timelines. No credentials, installs or third-party execution are needed.', '',
      f"Snapshot evidence: `{r['snapshot_ref']}`. Each source timeline has a compressed-file SHA-256; only post-T candidate outgoing rows are copied to this gzip snapshot, preserving original raw pointers. Ledger/address tables and coverage rows are frozen in the same snapshot. Source responses remain under their original raw directories. The edge CSV has transaction raw references, source explorer URLs, exact amounts, price observation time/raw references and all competing source label claims.", '',
      '## Definitions and limits', '',
      '- The unit is a chain-address pair from addresses.csv. T is the start of its first-listed date in Eastern Time; intraday publication order is unknown. The requested after-T window continues after removals; that is not a claim of continuing sanctions.',
      '- Include successful positive native transfers and exact-contract/decimal-allowlisted tokens. Unknown tokens remain in the CSV as unpriced; a token symbol cannot establish value. No USD=1 stablecoin assumption. Prices use price.usd(), hourly observations when fresh, otherwise daily; every row records the actual observation time. No interpolation or today-price backfill.',
      '- Main Sankey excludes source Tornado pool/router contracts, same-address transfers and priced values below USD 1. Functional Tornado source classification uses the labels lookup. Pool beneficiary/relayer splits are decoded from saved events and shown separately. Transfers between different addresses sharing an OFAC UID remain visible and flagged.',
      '- Single-source UTXO transactions retain each non-return output. Mixed-input outputs appear as candidate evidence with included_in_total=false; their full values are never attributed to the listed input. The listed address net debit excluding its fetcher-allocated fee appears once as an unlabelled/unallocated edge. Change to the same address is excluded; change to a new address cannot be identified. These are address transfers, not proof of external economic payments.',
      '- XRPL net balance debits without a proven recipient stay unallocated. SOL balance adjustments are excluded when is_transfer=false. Unreadable JSON/gzip files are skipped and counted; .tmp/.part files are ignored and counted. A valid incomplete history is retained with complete=false. Missing transfer timestamps are excluded and counted; no inferred timestamp is used.',
      '- Destination roles: mixer, bridge, dex, cex_deposit, cex_hot, other_sanctioned, issuer, defi_other, unlabelled. Conflicting functional roles become unlabelled. other_sanctioned requires its source validity interval at transfer time. Generic exchange names do not prove deposit/hot roles. Public labels are leads, not ownership findings; historical service-label validity is usually unknown.',
      '- Each program-tagged edge is split equally across its distinct program tags in the program view; the chain view assigns it once. Both link sets conserve the same total and are alternatives. Site mapping folds cex_hot into cex_deposit, issuer/defi_other into unlabelled. Stocks still_there/frozen are omitted from a gross-flow Sankey to avoid mixing units.', '',
      f"Excluding exchange-scale source addresses (>10,000 distinct transaction hashes), the wallet total is **${s['without_exchange_scale_usd']['value']:,.2f} USD at transfer time**. Separate source-Tornado gross outflows are **${s['tornado_source_contract_outflows_usd_separate']['value']:,.2f} USD at transfer time**, with timestamp/token gaps. There are **{s['unpriced_edges']['value']:,} unpriced evidence edges** and **${s['unallocated_destination_usd']['value']:,.2f} USD at transfer time** with unallocated recipients.", '',
      '## Candidate findings', '']
    for f in r['findings']:
        lines += ['### '+f['id'], '', f['sentence'], '', '**Unit/valuation:** '+f['amount']['unit']+'; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** '+f['confidence'], '']
        for source in f.get('context_sources',[]):
            lines += [f"Context source: [{source['source_url']}]({source['source_url']}); `{source['raw_ref']}`.", '']
        for e in f['examples']:
            lines += [f"- [{e['hash']}]({e['source_url']}) — {e['time_utc']}; price observed {e['valued_at']}; `{e['raw_ref']}`."]
        lines.append('')
    lines += ['## First-hop destination classes', '', '| Class | USD at transfer time | Edges |', '| --- | ---: | ---: |']
    for row in s['classes']: lines.append(f"| {row['class']} | {row['usd']['value']:,.2f} | {row['events']['value']:,} |")
    lines += ['', '## Named first-hop destinations', '',
      'Names below are verbatim public-source labels or OFAC names. They establish a lookup match, not current ownership or legal knowledge. USD is valued at transfer time; labels may lack historical validity. Full source claims and example transactions are in top_named_destinations in results/flows.json.', '',
      '| Source label | Chain | Class | USD at transfer time | Label confidence |', '| --- | --- | --- | ---: | --- |']
    for dest in r['top_named_destinations'][:12]:
        name=dest['label'].replace('|','\\|')
        confidence=', '.join(sorted({c['confidence'] for c in dest['label_claims']}))
        lines.append(f"| {name} | {dest['chain']} | {dest['class']} | {dest['usd']['value']:,.2f} | {confidence} |")
    lines += ['', '## Multi-hop coverage and rule', '', HOP_RULE, '',
      f"Largest-value selection: **{sel['selected_count']['value']} destination chain-address pairs**, representing **${sel['selected_usd']['value']:,.2f} / ${sel['unlabelled_usd']['value']:,.2f} unlabelled first-hop USD at transfer time ({sel['achieved_share']['value']:.2%})**. Target ≥80%, cap 400; target met: **{sel['target_met']}**. Unallocated synthetic destinations cannot be traced and remain in the denominator. Selection is across all covered chains; unsupported chains are reported, not silently dropped.", '',
      f"Attempted selected destinations: **{r['trace']['seed_addresses_attempted']['value']} chain-address pairs**; path outcomes: `{json.dumps(r['trace']['outcomes'],sort_keys=True)}`. The full trace bundle is `{r['trace']['bundle_ref']}`. Original first-hop USD weights are not amounts proven received by downstream services. Paths stop at any labelled class; a bridge/DEX terminal is censored for mixer/CEX reachability and asset conversions are not guessed.", '',
      'Keyless GET requests only: Blockscout for supported EVM networks, Trezor Blockbook for supported UTXO chains, TronGrid for Tron. At most one request start per host per 1.25 seconds, bounded exponential backoff on 429, resumable successful raw caching. No Etherscan requests. Errors, pagination limits, host circuit-breaks and unknown ordering are explicit terminal outcomes; these must not be interpreted as zero hops or no service reached.', '',
      '### First mixer/CEX reached (conditional on observed paths)', '',
      '| Class | Hops including first receipt | Paths | Original seed USD weight at first-transfer time |',
      '| --- | ---: | ---: | ---: |']
    for row in r['trace']['hop_distribution_to_first_mixer_cex']:
        if row['paths']['value']:
            lines.append(f"| {row['class']} | {row['hops']} | {row['paths']['value']} | {row['seed_weight_usd']['value']:,.2f} |")
    lines += ['', 'Seed weights are not downstream amounts received. No CEX label reached within checked paths is a censored observation, not proof no exchange was used. Terminal txs and full intermediate paths, amounts and labels are retained in the trace bundle.', '',
      '## Per-chain coverage (within data checked)', '', '| Chain | Ledger pairs | Readable timelines | Complete histories | Missing | Untrackable | USD at transfer time |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in r['coverage']['per_chain']:
        lines.append('| '+row['chain']+' | '+' | '.join(str(row[k]['value']) for k in ('ledger_addresses','timelines_readable','complete_histories','missing','untrackable'))+f" | {row['outflow_usd']['value']:,.2f} |")
    lines += ['', f"Unreadable files: {r['coverage']['unreadable_files']['value']}; in-progress files ignored: {r['coverage']['partial_files_ignored']['value']}; candidate outgoing rows without exact time: {r['coverage']['outgoing_rows_missing_exact_time']['value']}. Full per-address source coverage notes and missing ranges are in the snapshot.", '',
      '## What this adds to prior work', '',
      'Liu et al. arXiv 2507.11721v2 already trace Ethereum destinations, bridges and service interactions using proportional exposure; Zola et al. 2409.10031 already examine Bitcoin one/two-step service graphs. This output supplies a public-ledger chain-address cohort, transfer-time valuation, source-linked first-hop Sankey alternatives, temporal label handling and an explicit five-hop largest-output path heuristic with failed/partial paths retained. It does not claim a new tracing invention, full-chain coverage, causality, or parity with vendors’ private clusters. See docs/PRIOR_ART.md and the binding docs/DEFINITIONS.md.', '',
      '## Execution scope and open uncertainties', '',
       '',
      'Coverage is uneven by chain and changes during acquisition. Sparse Tron/BTC CEX labels can make a service appear unlabelled. Historical label deployment/ownership is usually unverified. Successful API pagination is not independent chain-node validation; provider result caps can prevent ordering proof. Gross same-entity movements and address reuse can dominate a Sankey without measuring new money. First-hop unknown-token quantities cannot be valued safely. Exact publication-time ambiguity, incomplete histories and post-delisting observations limit headline interpretation.', '',
      'Research, not legal or compliance advice. “Received funds from a sanctioned address” describes an observed chain relationship, not unlawful conduct. Exchanges may have frozen or reported funds. Names in outputs are verbatim source labels or OFAC names; no unlabelled address owner is inferred.', '']
    lines += """## Public chart grouping

The compact chart labels `unlabelled + defi_other` as **Other / unclassified** and `cex_deposit + cex_hot` as **Exchange-labelled address**. It separately displays the original unknown-role share and original DeFi, deposit and hot-wallet subtotals from `results/flows.json#summary.classes`, valued at each transfer time. Gross first-hop transfers can count funds repeatedly. The public export derives these fields with `scripts/release/presentation.py`; raw API captures are omitted for size and request identities can be re-fetched through the pipeline.
""".splitlines() + ['']
    return '\n'.join(lines).encode()


def verify(r, edges):
    target=r['summary']['wallet_outflows_usd']['value']
    for graph in r['sankey'].values():
        if abs(sum(l['value'] for l in graph['links'])-target)>0.02: raise AssertionError('Sankey conservation failed')
    if any(e['usd'] and (not e['valued_at'] or not e['price_raw_ref']) for e in edges): raise AssertionError('Missing USD price evidence')
    if any(not e['raw_ref'] for e in edges): raise AssertionError('Missing transfer raw evidence')
    for ref in {e['raw_ref'].split('#')[0] for e in edges}:
        if not (ROOT/ref).is_file(): raise AssertionError('Missing raw response '+ref)


def self_test():
    tx={'amount':'8','direction':'out','block':1,'inputs':[{'addresses':['a'],'value_sat':1000000000}],
        'outputs':[{'addresses':['a'],'value_sat':100000000},{'addresses':['b'],'value_sat':800000000}]}
    es=split_transfer('BTC','a',tx); assert len(es)==1 and es[0][0]=='b' and es[0][1]==8 and es[0][3]
    tx['inputs'].append({'addresses':['c'],'value_sat':100000000})
    es=split_transfer('BTC','a',tx); assert sum(e[3] for e in es)==1 and es[-1][0]=='__mixed_input_utxo__'
    assert not split_transfer('ETH','a',{'amount':'99','direction':'out','success':False})
    assert token_asset('ETH',{'asset':'0x'+'a'*40,'symbol':'USDT','decimals':6})[0] is None
    assert token_asset('TRX',{'asset':'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t','symbol':'FAKE','decimals':6})[0]=='USDT'
    assert designation('2022-08-08').isoformat()=='2022-08-08T04:00:00+00:00'
    graph=sankey([{'chain':'ETH','programs':'A;B','destination_class':'cex_hot','usd':'10'}],'program')
    assert sum(l['value'] for l in graph['links'])==10 and len(graph['links'])==2
    assert not split_transfer('SOL','a',{'amount':'9','direction':'out','is_transfer':False})
    assert split_transfer('XRP','a',{'amount':'9','direction':'out','counterparties':['b']})[0][0].startswith('__')
    print('PASS: UTXO attribution/change, fake symbols, failed transfers, SOL adjustments, XRPL recipients, ET designation, Sankey conservation')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test: self_test(); return 0
    published=load(RESULT) if RESULT.exists() else None
    if args.check or args.resume:
        if not published: p.error('No saved result; first run without --check/--resume')
        snapshot_ref=published['snapshot_ref'];snap=load(ROOT/snapshot_ref)
        for path,expected in (snap['shared_hashes']|snap['price_hashes']).items():
            if sha((ROOT/path).read_bytes()) != expected: raise RuntimeError('Shared dependency changed; run fresh flows.py: '+path)
    else:
        snap=snapshot();snapshot_ref=archive(snap,'snapshots')
    edges,rejects=build_edges(snap)
    pointer=RAW/'trace_latest.json.gz';bundle=load(pointer) if pointer.exists() else None
    if bundle and bundle.get('snapshot_ref') != snapshot_ref: bundle=None
    r=build_result(snap,snapshot_ref,edges,rejects,bundle);verify(r,edges)
    from scripts.lib.fetch_status import apply_status, report_status
    r=apply_status(r,ROOT,"flows")
    outputs={RESULT:json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False).encode()+b'\n', EDGES:render_csv(edges),DOC:report_status(render_doc(r),r)}
    if args.check:
        different=[rel(path) for path,data in outputs.items() if not path.exists() or path.read_bytes()!=data]
        if different: print('DIFF: '+', '.join(different));return 1
        print('PASS: pinned-snapshot JSON, edge CSV, report, source references and Sankey conservation reproduce offline')
    else:
        for path,data in outputs.items():atomic(path,data)
        print(json.dumps({'provisional':r['provisional'],'timeline_count':r['timeline_count'],'summary':r['summary'],'trace_selected':r['trace_selection']['selected_count']},indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())
