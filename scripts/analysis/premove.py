#!/usr/bin/env python3
"""Offline, provisional own-history pre-designation outflow analysis (see PREMOVE.md).

Run with the project Python. --check verifies the saved snapshot; --self-test uses
synthetic observations only. Writes only this analysis's result and report paths.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
import argparse
import bisect
import collections
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import random
import os
import tempfile
from functools import lru_cache
import statistics
import zlib
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.prices import price as prices
from scripts.labels.lookup import label

UTC = dt.timezone.utc
ET = ZoneInfo('America/New_York')
N = 12
DRAWS = 9999
SEED = 20261023
OUT = ROOT / 'results/premove.json'
DOC = ROOT / 'docs/analysis/PREMOVE.md'
MARKER = '## Implementation and snapshot results'
NATIVE = {'ETH':'ETH','ARB':'ETH','BSC':'BNB','ETC':'ETC','OP':'ETH','BASE':'ETH',
          'POLYGON':'POL','AVAX':'AVAX','BTC':'BTC','BCH':'BCH','BSV':'BSV',
          'TRX':'TRX','LTC':'LTC','DOGE':'DOGE','DASH':'DASH','ZEC':'ZEC',
          'XVG':'XVG','XRP':'XRP','SOL':'SOL','BNB':'BNB'}
# Contract identity, not explorer-provided symbol, authorizes token valuation.
TOKENS = {
 'ETH': {'0xdac17f958d2ee523a2206206994597c13d831ec7':('USDT',6),
         '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48':('USDC',6),
         '0x6b175474e89094c44da98b954eedeac495271d0f':('DAI',18),
         '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2':('ETH',18),
         '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599':('BTC',8)},
 'TRX': {'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t':('USDT',6),
         'TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8':('USDC',6)},
 'ARB': {'0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9':('USDT',6),
         '0xaf88d065e77c8cc2239327c5edb3a432268e5831':('USDC',6),
         '0xff970a61a04b1ca14834a43f5de4533ebddb5cc8':('USDC',6)},
 'OP': {'0x0b2c639c533813f4aa9d7837caf62653d097ff85':('USDC',6),
        '0x94b008aa00579c1307b0ef2c499ad98a8ce58e58':('USDT',6)},
 'BASE': {'0x833589fcd6edb6e08f4c7c32d4f71b54bda02913':('USDC',6)},
 'POLYGON': {'0xc2132d05d31c914a87c6611c10748aeb04b58e8f':('USDT',6),
             '0x3c499c542cef5e3811e1192ce70d8cc03d5c3359':('USDC',6)},
 'SOL': {'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v':('USDC',6)},
}
EVM = {'ETH','ARB','BSC','ETC','OP','BASE','POLYGON','AVAX'}


def metric(value, unit, valued_at=None):
    r = {'value': value, 'unit': unit}
    if valued_at is not None:
        r['valued_at'] = valued_at
    return r


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat().replace('+00:00','Z')


def timestamp(s):
    if not s:
        return None
    try:
        x = dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return x.replace(tzinfo=x.tzinfo or UTC).timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def dec(v):
    try:
        x = Decimal(str(v))
        return x if x.is_finite() else None
    except (InvalidOperation, TypeError):
        return None


def norm(chain, address):
    return address.lower() if chain in EVM or address.lower().startswith('bc1') else address


def split(v):
    return [a for a in (v or '').split(';') if a]


def relative(p):
    return p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else p.as_posix()


def fingerprint(p):
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def csv_rows(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def asset_info(chain, row):
    a = str(row.get('asset') or '')
    if chain in EVM and a.startswith('0x'):
        a = a.lower()
    if a == NATIVE.get(chain):
        return a, a, None
    found = TOKENS.get(chain,{}).get(a)
    if found:
        symbol, decimals = found
        # Reject malicious/misparsed decimal metadata even for a familiar contract.
        if row.get('decimals') is not None and str(row['decimals']) != str(decimals):
            return None
        return a, symbol, decimals
    return None


@lru_cache(maxsize=50000)
def quote(symbol, t):
    value, observed, source = prices.usd(symbol, iso(t))
    if value is None or not math.isfinite(value) or value <= 0:
        return None
    freq = '1h' if source.startswith('Binance') else '1d'
    resolved = prices.resolve_asset(symbol)
    row = prices._lookup_rows(resolved['symbol'], freq, dt.datetime.fromtimestamp(t, UTC))
    return {'price':value,'valued_at':observed,'source':source,
            'raw_ref':row['raw_ref'],'source_url':row['source_url']}


def explorer(chain, txhash):
    bases = {'BTC':'https://mempool.space/tx/','BCH':'https://blockchair.com/bitcoin-cash/transaction/',
             'BSV':'https://whatsonchain.com/tx/','LTC':'https://litecoinspace.org/tx/',
             'DOGE':'https://dogechain.info/tx/','DASH':'https://explorer.dash.org/insight/tx/',
             'ETH':'https://etherscan.io/tx/','ARB':'https://arbiscan.io/tx/',
             'BSC':'https://bscscan.com/tx/','ETC':'https://etc.blockscout.com/tx/',
             'OP':'https://optimistic.etherscan.io/tx/','BASE':'https://basescan.org/tx/',
             'POLYGON':'https://polygonscan.com/tx/','AVAX':'https://snowtrace.io/tx/',
             'TRX':'https://tronscan.org/#/transaction/','SOL':'https://solscan.io/tx/',
             'XRP':'https://livenet.xrpl.org/transactions/','BNB':'https://explorer.bnbchain.org/tx/'}
    return bases.get(chain,'') + txhash if chain in bases else None


def is_confirmed(chain, t):
    # TronGrid's confirmed TRC20 route does not return block numbers.
    return (bool(t.get('block')) or chain == 'TRX') and t.get('confirmed',True) is not False


def read_timeline(p):
    """A writer can atomically replace or partially write a file during this read."""
    try:
        b = p.read_bytes()
    except FileNotFoundError:
        return None, {'path':relative(p),'sha256':None,'status':'missing'}
    entry = {'path':relative(p),'sha256':hashlib.sha256(b).hexdigest()}
    try:
        x = json.loads(gzip.decompress(b) if p.suffix == '.gz' else b)
        if (not isinstance(x,dict) or not isinstance(x.get('txs'),list) or
            not isinstance(x.get('coverage'),dict) or not isinstance(x.get('chain'),str) or
            not isinstance(x.get('address'),str) or not isinstance(x.get('balance_now',[]),list)):
            raise ValueError('required txs/coverage schema absent')
    except (ValueError, OSError, EOFError, zlib.error, UnicodeError) as e:
        entry.update(status='unreadable_or_partial',error=type(e).__name__)
        return None, entry
    entry['status'] = 'readable'
    return x, entry


class History:
    def __init__(self, chain, x):
        self.chain = chain
        self.quality = collections.Counter()
        self.events = []
        self.outgoing = []
        self.deltas = collections.defaultdict(lambda: collections.defaultdict(Decimal))
        self.assets = {}
        self.bad_assets = set()
        self.raw_refs = set()
        first = []
        hashes = set()
        for i,t in enumerate(x['txs']):
            if not isinstance(t,dict):
                self.quality['malformed_rows'] += 1
                continue
            ts = timestamp(t.get('time_utc'))
            if not is_confirmed(chain,t):
                self.quality['unconfirmed_rows'] += 1
                continue
            if ts is None:
                self.quality['undated_confirmed_rows'] += 1
                continue
            first.append(ts)
            if t.get('hash'):
                hashes.add(t['hash'])
            direction = t.get('direction')
            amount = dec(t.get('amount'))
            if amount is None or amount < 0 or direction not in ('in','out','self') or not t.get('hash') or not t.get('raw_ref'):
                self.quality['malformed_rows'] += 1
                continue
            inf = asset_info(chain,t)
            if not inf:
                if amount > 0:
                    self.quality['unrecognised_asset_rows'] += 1
                continue
            asset,symbol,decimals = inf
            self.assets[asset] = symbol
            fee = dec(t.get('fee'))
            fee_asset = str(t.get('fee_asset') or NATIVE.get(chain) or asset)
            if fee is None:
                self.bad_assets.add(fee_asset)
                fee = Decimal(0)
            delta = amount if direction=='in' else -amount if direction=='out' else Decimal(0)
            self.deltas[asset][ts] += delta
            if fee > 0:
                self.deltas[fee_asset][ts] -= fee
                self.assets[fee_asset] = NATIVE.get(chain,fee_asset)
            success = t.get('success',True) is not False and str(t.get('status','')).lower() not in ('failed','failure','reverted')
            # Failed tx fees remain accounting deltas; transfer amount is ignored.
            if not success:
                self.deltas[asset][ts] -= delta
                continue
            if amount == 0 or direction != 'out' or t.get('is_transfer',True) is False:
                continue
            q = quote(symbol,ts)
            usd = float(amount)*q['price'] if q else None
            if usd is not None and usd < 1:
                self.quality['dust_outgoing_rows'] += 1
                continue
            e = {'ts':ts,'asset':asset,'symbol':symbol,'amount':str(amount),'usd':usd,'price':q,
                 'hash':t['hash'],'raw_ref':t['raw_ref'],'timeline_row':i,
                 'counterparties':t.get('counterparties',[])}
            self.outgoing.append(e)
            if q is None:
                self.quality['unpriced_recognised_outgoing_rows'] += 1
        self.first = min(first) if first else None
        self.tx_count = len(hashes)
        self.large = len(hashes)>10000 or x['coverage'].get('huge_address',False) or x['coverage'].get('reported_history_records',0)>10000
        cov = x['coverage']
        self.end = timestamp(cov.get('checked_through_time') or cov.get('to_time') or x.get('fetched_at'))
        self.complete = cov.get('complete') is True and not self.quality['malformed_rows'] and not self.quality['undated_confirmed_rows']
        self.outgoing.sort(key=lambda e:(e['ts'],e['hash'],e['timeline_row']))
        self.out_times = [e['ts'] for e in self.outgoing]
        self.streams = {}
        self.reconciliation = []
        observed = {}
        for b in x.get('balance_now',[]):
            if not isinstance(b,dict):continue
            inf = asset_info(chain,b)
            if inf and dec(b.get('amount')) is not None:
                observed[inf[0]] = b
        for asset,symbol in self.assets.items():
            times=[]; cumulative=[]; total=Decimal(0); minimum=Decimal(0)
            for t,v in sorted(self.deltas[asset].items()):
                total+=v;minimum=min(minimum,total);times.append(t);cumulative.append(total)
            b=observed.get(asset)
            obs=dec(b['amount']) if b else None
            # Observe at exactly the history head where a block is supplied.
            compatible = bool(b) and (not b.get('block') or not cov.get('to_block') or int(b['block'])==int(cov['to_block']))
            tol=Decimal('0.00000001') if chain in {'BTC','BCH','BSV','LTC','DASH','DOGE','ZEC','XVG'} else Decimal('0.000000000001')
            good = compatible and obs is not None and abs(total-obs)<=tol and minimum>=-tol and asset not in self.bad_assets
            self.reconciliation.append({'asset':asset,'symbol':symbol,'reconstructed':str(total),
                'observed':str(obs) if obs is not None else None,'minimum':str(minimum),'pass':bool(good),
                'raw_ref':b.get('raw_ref') if b else None,'compatible_snapshot':compatible})
            self.streams[asset]=(times,cumulative,good)
        self.balance_usable = self.complete and bool(self.streams) and all(v[2] for v in self.streams.values())

    def opening(self, asset, start):
        times,values,_ = self.streams[asset]
        k=bisect.bisect_left(times,start)-1
        return values[k] if k>=0 else Decimal(0)

    def window(self, start, end):
        a=bisect.bisect_left(self.out_times,start);b=bisect.bisect_left(self.out_times,end)
        events=self.outgoing[a:b]
        priced=[e for e in events if e['usd'] is not None]
        unknown=len(events)-len(priced)
        usd=sum(e['usd'] for e in priced)
        any_out=1 if priced else None if unknown else 0
        ratio=None;den=None
        if self.balance_usable and not unknown:
            den=0.;num=0.;ok=True
            native=collections.defaultdict(Decimal)
            for e in priced:native[e['asset']]+=Decimal(e['amount'])
            for asset,symbol in self.assets.items():
                opening=max(Decimal(0),self.opening(asset,start))
                if opening==0 and native[asset]==0:continue
                q=quote(symbol,start)
                if q is None:ok=False;break
                den+=float(opening)*q['price'];num+=float(native[asset])*q['price']
            if ok and den>0:ratio=num/den
            if not ok:den=None
        return {'start':iso(start),'end':iso(end),'any_outflow':any_out,
                'outflow_usd':None if unknown else usd,'priced_subtotal_usd':usd,
                'balance_turnover':ratio,'opening_balance_usd':den,
                'unpriced_events':unknown,'events':events}


def rank_values(values):
    ordered=sorted(values);m=len(values)
    return [(bisect.bisect_left(ordered,x)+bisect.bisect_right(ordered,x))/(2*m) for x in values]


def summarize_window(w, events=False):
    r = {'start':w['start'],'end':w['end'],
         'any_outflow':metric(w['any_outflow'],'binary'),
         'outflow_usd':metric(w['outflow_usd'],'usd','at each transfer time; price observation retained in examples'),
         'priced_subtotal_usd':metric(w['priced_subtotal_usd'],'usd','at each transfer time'),
         'balance_turnover':metric(w['balance_turnover'],'ratio'),
         'opening_balance_usd':metric(w['opening_balance_usd'],'usd',w['start']),
         'unpriced_events':metric(w['unpriced_events'],'events'),
         'outgoing_transfer_rows':metric(len(w['events']),'events')}
    if events:r['events']=[evidence(e) for e in w['events']]
    return r


def evidence(e, chain=None):
    r={k:v for k,v in e.items() if k not in ('ts','counterparties')}
    r['time_utc']=iso(e['ts'])
    r['amount']=metric(e['amount'],'native:'+e['symbol'])
    r['outflow_usd']=metric(r.pop('usd'),'usd',r['time_utc'])
    if chain:r.update(chain=chain,explorer_url=explorer(chain,e['hash']))
    return r


def evaluate(h, meta, shift, width):
    event=dt.datetime.fromisoformat(meta['listed_date']).replace(tzinfo=ET)-dt.timedelta(days=shift)
    end=event.timestamp();start=(event-dt.timedelta(days=width)).timestamp()
    if not h.complete:return None,'incomplete_or_malformed_history'
    if h.first is None:return None,'no_observed_history'
    if h.end is None or h.end<end:return None,'event_not_covered_through_T'
    bases=[];k=0
    while True:
        b_end=event-dt.timedelta(days=35+7*k);b_start=b_end-dt.timedelta(days=width)
        if b_start.timestamp()<h.first:break
        bases.append(h.window(b_start.timestamp(),b_end.timestamp()));k+=1
    if len(bases)<N:return None,'fewer_than_12_baseline_weeks'
    real=h.window(start,end)
    tests={};samples={}
    for key in ('any_outflow','balance_turnover','outflow_usd'):
        v=[w[key] for w in bases]+[real[key]]
        if any(x is None for x in v):continue
        r=rank_values(v);emp=(1+sum(x>=v[-1] for x in v[:-1]))/len(v)
        samples[key]=r
        tests[key]={'real':v[-1],'baseline_mean':statistics.mean(v[:-1]),
          'baseline_median':statistics.median(v[:-1]),'baseline_max':max(v[:-1]),
          'midrank':r[-1],'upper_tail_p':emp,
          'unit':'usd' if key=='outflow_usd' else 'ratio' if key=='balance_turnover' else 'binary',
          'valued_at':'at each transfer time' if key=='outflow_usd' else None}
    inactive=not any(w['events'] for w in bases+[real])
    return {'id':meta['id'],'shift_days':shift,'window_days':width,'baseline_windows':len(bases),
            'inactive':inactive,'tests':tests,'real':summarize_window(real),
            'baseline_series':{'order':'newest first; weekly endpoints in Eastern time',
                 'first_end_utc':bases[0]['end'],
                 'columns':{k:[w[k] for w in bases] for k in ('any_outflow','outflow_usd','balance_turnover')}},
            '_samples':samples,'_real_events':real['events']},None


class DSU:
    def __init__(self,n):self.p=list(range(n))
    def find(self,x):
        while self.p[x]!=x:self.p[x]=self.p[self.p[x]];x=self.p[x]
        return x
    def union(self,a,b):self.p[self.find(a)]=self.find(b)


def components(rows, metas, partition='action_entity'):
    d=DSU(len(rows));owners={}
    for i,r in enumerate(rows):
        m=metas[r['id']];keys=[]
        if partition in ('action','action_entity'):keys += ['a:'+a for a in m['action_urls'] or [m['listed_date']]]
        if partition in ('entity','action_entity'):keys += ['e:'+e for e in m['entity_uids']]
        for k in keys:
            if k in owners:d.union(i,owners[k])
            else:owners[k]=i
    groups=collections.defaultdict(list)
    for i,r in enumerate(rows):groups[d.find(i)].append(r)
    return list(groups.values())


def pooled(rows, metas, key, partition='action_entity', draws=DRAWS):
    rows=[r for r in rows if key in r['tests']]
    if not rows:return {'addresses':metric(0,'addresses'),'clusters':metric(0,'clusters'),'p_one_sided':None}
    groups=components(rows,metas,partition)
    obs=statistics.mean(statistics.mean(r['tests'][key]['midrank']-.5 for r in g) for g in groups)
    # Quantile coupling within a cluster is a stated positive-dependence model,
    # not a claim of an exact joint randomization under arbitrary dependence.
    nulls=[]
    for g in groups:
        distributions=[sorted(r['_samples'][key]) for r in g]
        # Sweep only changes between distinct tied ranks; identical windows
        # have no jump. This is algebraically the same quantile coupling.
        jumps=collections.defaultdict(float)
        value=sum(v[0]-.5 for v in distributions)/len(distributions)
        for v in distributions:
            for i in range(1,len(v)):
                if v[i]!=v[i-1]:jumps[i/len(v)]+=(v[i]-v[i-1])/len(distributions)
        cuts=[];vals=[]
        for cut,delta in sorted(jumps.items()):
            cuts.append(cut);vals.append(value);value+=delta
        cuts.append(1.);vals.append(value)
        nulls.append((cuts,vals))
    rng=random.Random(SEED);ge=0
    for _ in range(draws):
        score=0.
        for cuts,vals in nulls:score+=vals[min(bisect.bisect_right(cuts,rng.random()),len(vals)-1)]
        if score/len(groups)>=obs-1e-12:ge+=1
    return {'addresses':metric(len(rows),'addresses'),'clusters':metric(len(groups),'clusters'),
            'partition':partition,'cluster_equal_weight_centered_midrank':metric(obs,'rank_score'),
            'address_mean_midrank':metric(statistics.mean(r['tests'][key]['midrank'] for r in rows),'rank_percentile'),
            'p_one_sided':(ge+1)/(draws+1),'draws':metric(draws,'permutations'),
            'few_clusters':len(groups)<10,
            'observed_active_addresses':metric(sum(r['real']['any_outflow']['value']==1 for r in rows),'addresses'),
            'mean_real':metric(statistics.mean(r['tests'][key]['real'] for r in rows),
                               'usd' if key=='outflow_usd' else 'ratio' if key=='balance_turnover' else 'share',
                               'at each transfer time' if key=='outflow_usd' else None),
            'mean_baseline':metric(statistics.mean(r['tests'][key]['baseline_mean'] for r in rows),
                               'usd' if key=='outflow_usd' else 'ratio' if key=='balance_turnover' else 'share',
                               'at each transfer time' if key=='outflow_usd' else None)}


def holm(tests):
    ordered=sorted((v['p_one_sided'],k) for k,v in tests.items() if v['p_one_sided'] is not None)
    running=0.
    for i,(p,k) in enumerate(ordered):
        running=max(running,min(1.,(len(tests)-i)*p))
        tests[k]['p_holm_primary_three_metrics']=running


def strata(rows,metas):
    groups=collections.defaultdict(list)
    for r in rows:
        m=metas[r['id']]
        groups['chain:'+m['chain']].append(r)
        for p in m['programs']:groups['program:'+p].append(r)
        for a in m['action_urls'] or [m['listed_date']]:groups['action:'+a].append(r)
    out=[]
    for name,items in sorted(groups.items()):
        out.append({'stratum':name,'addresses':metric(len(items),'addresses'),
            'inactive_addresses':metric(sum(r['inactive'] for r in items),'addresses'),
            'tests':{k:pooled(items,metas,k) for k in ('any_outflow','balance_turnover','outflow_usd')},
            'source_url':sorted({a for r in items for a in metas[r['id']]['action_urls']})})
    return out


def input_paths():
    fixed=['data/addresses.csv','data/ledger.csv','data/actions.csv','docs/DEFINITIONS.md',
           'scripts/prices/price.py','scripts/labels/lookup.py','scripts/labels/policy.py',
           'data/labels/labels.sqlite','data/labels/labels.csv','scripts/analysis/premove.py',
           'scripts/prices/contracts.json']
    return sorted({str(p) for p in fixed}|{relative(p) for p in (ROOT/'data/prices').glob('*.csv.gz')}|
                  {relative(p) for p in (ROOT/'data/reference').glob('*.csv')})


def metadata(addresses, ledger, actions):
    by_uid=collections.defaultdict(list)
    for r in ledger:
        for ch in split(r.get('chains') or r['chain']):by_uid[ch,norm(ch,r['address_normalized'])].append(r)
    metas={}
    for a in addresses:
        chain=a['chain'].upper();address=norm(chain,a['address_normalized']);key=chain+':'+address
        rows=by_uid[chain,address]
        first=a['first_listed_date']
        initial=[r for r in rows if r['listed_date']==first]
        urls=sorted({r['listed_action_url'] for r in initial if r.get('listed_action_url')})
        metas[key]={'id':key,'chain':chain,'address':address,'listed_date':first,
                    'trackable':a['trackable'].lower()=='true',
                    'entity_uids':sorted(set(split(a.get('sdn_uids') or a.get('all_entity_uids')))),
                    'entities':[{'uid':uid,'name':name} for uid,name in sorted({(r['sdn_uid'],r['sdn_name']) for r in rows})],
                    'programs':split(a['programs']),'action_urls':urls,
                    'tornado':any('TORNADO' in r['sdn_name'].upper() for r in rows),
                    'source_url':a.get('source_url'),'raw_ref':a.get('raw_ref'),
                    'action_evidence':[{'source_url':r.get('listed_action_url'),'raw_ref':r.get('listed_raw_ref')} for r in initial],
                    'timeline_path':f'data/timelines/{chain.lower()}/{address}.json.gz'}
    return metas


def run(saved=None):
    paths=list(saved['input_hashes']) if saved else input_paths()
    hashes={p:fingerprint(ROOT/p) for p in paths}
    if saved and hashes!=saved['input_hashes']:
        changed=[p for p in paths if hashes[p]!=saved['input_hashes'][p]]
        raise RuntimeError('input drift; rerun to adopt new snapshot: '+', '.join(changed))
    meta=metadata(csv_rows(ROOT/'data/addresses.csv'),csv_rows(ROOT/'data/ledger.csv'),csv_rows(ROOT/'data/actions.csv'))
    results=collections.defaultdict(list);exclusions=collections.defaultdict(collections.Counter)
    inventory=[];coverage=[];qualities=collections.Counter();snapshot={}
    expected={e['path']:e for e in saved['timeline_inventory']} if saved else {}
    for j,(key,m) in enumerate(sorted(meta.items())):
        if j%100==0:print(f'loading {j+1}/{len(meta)} listed pairs',file=sys.stderr,flush=True)
        p=ROOT/m['timeline_path']
        if not p.exists() and p.with_suffix('').exists():p=p.with_suffix('')
        # Tornado rows are inventoried without decoding their very large histories.
        if m['tornado']:
            sha=fingerprint(p);entry={'path':relative(p),'sha256':sha,'status':'tornado_excluded' if sha else 'missing'};x=None
        elif not m['trackable']:
            sha=fingerprint(p);entry={'path':relative(p),'sha256':sha,'status':'untrackable_excluded' if sha else 'missing'};x=None
        else:x,entry=read_timeline(p)
        if x is not None and (x['chain'].upper()!=m['chain'] or norm(m['chain'],x['address'])!=m['address']):
            entry['status']='schema_partial';x=None
        if saved and (entry['path'] not in expected or entry['sha256']!=expected[entry['path']]['sha256'] or entry['status']!=expected[entry['path']]['status']):
            raise RuntimeError('timeline drift; rerun to adopt new snapshot: '+relative(p))
        inventory.append(entry)
        cov={'id':key,'chain':m['chain'],'trackable':m['trackable'],'tornado':m['tornado'],
             'timeline_status':entry['status'],'raw_ref':m['raw_ref'],'source_url':m['source_url']}
        if x is None:
            reason='tornado_excluded' if m['tornado'] else 'untrackable' if not m['trackable'] else entry['status']
            cov['reason']=reason;coverage.append(cov)
            for shift in (0,60,90,180):
                for width in (7,3,1):exclusions[shift,width][reason]+=1
            continue
        if x.get('chain','').upper()!=m['chain'] or norm(m['chain'],x.get('address',''))!=m['address']:
            entry['status']='schema_partial';cov['reason']='identity_mismatch';coverage.append(cov)
            for shift in (0,60,90,180):
                for width in (7,3,1):exclusions[shift,width]['identity_mismatch']+=1
            continue
        h=History(m['chain'],x);qualities.update(h.quality)
        m['exchange_scale']=h.large
        cov.update(history_complete=h.complete,tx_hashes=metric(h.tx_count,'transactions'),
                   first_observed=iso(h.first) if h.first else None,observed_through=iso(h.end) if h.end else None,
                   exchange_scale=h.large,quality=dict(h.quality),balance_usable=h.balance_usable,
                   balance_reconciliation=h.reconciliation,coverage_notes=x['coverage'].get('notes',[]),
                   raw_history_refs=x['coverage'].get('raw_refs',[]),
                   raw_coverage=x['coverage'])
        coverage.append(cov)
        for shift in (0,60,90,180):
            for width in (7,3,1):
                result,reason=evaluate(h,m,shift,width)
                if result:results[shift,width].append(result)
                else:exclusions[shift,width][reason]+=1
    print('timeline pass complete; pooling clustered rank tests',file=sys.stderr,flush=True)
    tests={};common={}
    for width in (7,3,1):
        common[width]=set.intersection(*(set(r['id'] for r in results[s,width]) for s in (0,60,90,180)))
    for shift in (0,60,90,180):
        for width in (7,3,1):
            rows=results[shift,width];kk=f'shift_{shift}_window_{width}'
            primary={k:pooled(rows,meta,k) for k in ('any_outflow','balance_turnover','outflow_usd')}
            if shift==0 and width==7:holm(primary)
            tests[kk]={'shift_days':metric(shift,'days'),'window_days':metric(width,'days'),
                'eligible_addresses':metric(len(rows),'addresses'),
                'inactive_addresses':metric(sum(r['inactive'] for r in rows),'addresses'),
                'active_addresses':metric(sum(not r['inactive'] for r in rows),'addresses'),
                'exclusions':{k:metric(v,'addresses') for k,v in sorted(exclusions[shift,width].items())},
                'pooled':primary,
                'common_cohort':{k:pooled([r for r in rows if r['id'] in common[width]],meta,k) for k in ('any_outflow','balance_turnover','outflow_usd')}}
            if shift==0:
                tests[kk]['without_exchange_scale']={k:pooled([r for r in rows if not meta[r['id']]['exchange_scale']],meta,k) for k in ('any_outflow','balance_turnover','outflow_usd')}
                tests[kk]['active_histories']={k:pooled([r for r in rows if not r['inactive']],meta,k) for k in ('any_outflow','balance_turnover','outflow_usd')}
                tests[kk]['action_only']={k:pooled(rows,meta,k,'action') for k in ('any_outflow','balance_turnover','outflow_usd')}
                tests[kk]['entity_only']={k:pooled(rows,meta,k,'entity') for k in ('any_outflow','balance_turnover','outflow_usd')}
    real=results[0,7]
    extremes=[]
    for r in sorted((r for r in real if 'outflow_usd' in r['tests'] and r['tests']['outflow_usd']['real']>0),
                    key=lambda r:(r['tests']['outflow_usd']['upper_tail_p'],-r['tests']['outflow_usd']['real']))[:20]:
        m=meta[r['id']];examples=[];seen=set()
        for e in sorted(r['_real_events'],key=lambda e:-(e['usd'] or 0)):
            if e['hash'] in seen:continue
            seen.add(e['hash']);item=evidence(e,m['chain'])
            item['counterparty_label_leads']=[]
            for counter in e['counterparties'][:2]:
                try:claims=label(m['chain'],counter)
                except (FileNotFoundError, OSError):claims=[]
                item['counterparty_label_leads'].extend({'address':counter,'role':'transaction participant; economic recipient not established',**{k:c.get(k) for k in ('label','class','source_url','raw_ref','confidence','valid_from','valid_to')}} for c in claims[:2])
            examples.append(item)
            if len(examples)==3:break
        extremes.append({'id':r['id'],'address':m['address'],'chain':m['chain'],'entities':m['entities'],
            'listed_date':m['listed_date'],'action_urls':m['action_urls'],'action_evidence':m['action_evidence'],
            'programs':m['programs'],'exchange_scale':m['exchange_scale'],
            'baseline_windows':metric(r['baseline_windows'],'windows'),'tests':r['tests'],
            'real_window':r['real'],'example_txs':examples,'raw_ref':m['timeline_path'],
            'confidence':'Exploratory selected case; address activity within saved coverage, no evidence of advance knowledge or legal violation.'})
    per_chain=[]
    for chain in sorted({m['chain'] for m in meta.values()}):
        items=[c for c in coverage if c['chain']==chain]
        per_chain.append({'chain':chain,'ledger_addresses':metric(len(items),'addresses'),
            'trackable_addresses':metric(sum(c['trackable'] for c in items),'addresses'),
            'with_timeline':metric(sum(c['timeline_status']!='missing' for c in items),'addresses'),
            'readable_wallet_timelines':metric(sum(c['timeline_status']=='readable' for c in items),'addresses'),
            'complete_wallet_histories':metric(sum(c.get('history_complete',False) for c in items),'addresses'),
            'eligible_primary':metric(sum(meta[r['id']]['chain']==chain for r in real),'addresses'),
            'source_url':'data/addresses.csv','raw_ref':[c['raw_ref'] for c in items[:1]]})
    # Internal sample distributions stay in memory; save full baseline metrics so
    # every reported rank/mean can also be independently recomputed from JSON.
    address_results=[]
    for (shift,width),rows in sorted(results.items()):
        for r in rows:
            clean={k:v for k,v in r.items() if not k.startswith('_')}
            clean.update({k:meta[r['id']][k] for k in ('chain','address','entities','entity_uids','programs','action_urls','listed_date','source_url','raw_ref')})
            clean['raw_ref']=meta[r['id']]['timeline_path'];address_results.append(clean)
    drift=[p for p,v in hashes.items() if fingerprint(ROOT/p)!=v]
    output={'schema_version':1,'provisional':True,
        'generated_at_utc':saved['generated_at_utc'] if saved else dt.datetime.now(UTC).isoformat(),
        'preregistration_sha256':hashlib.sha256(DOC.read_text().split(MARKER)[0].encode()).hexdigest(),
        'script':'scripts/analysis/premove.py','design':'docs/analysis/PREMOVE.md',
        'method':{'minimum_baseline_weeks':N,'seed':SEED,'draws':DRAWS,
                  'primary_window_days':7,'buffer_days':30,'baseline_first_endpoint_days_before_T':35,
                  'T':'00:00 America/New_York on identifier first-publication date',
                  'cluster_method':'connected components joining shared first-publication action OR entity',
                  'permutation_dependence':'common-uniform empirical-quantile coupling within cluster; conditional diagnostic'},
        'input_hashes':hashes,'timeline_inventory':inventory,
        'baseline_series_units':{'any_outflow':'binary','outflow_usd':'usd at each transfer time','balance_turnover':'unbounded turnover ratio'},
        'inputs_changed_during_run':drift,
        'coverage':{'ledger_addresses':metric(len(meta),'addresses'),
            'ledger_address_entity_rows':metric(len(csv_rows(ROOT/'data/ledger.csv')),'address_entity_pairs'),
            'trackable_addresses':metric(sum(m['trackable'] for m in meta.values()),'addresses'),
            'untrackable_addresses':metric(sum(not m['trackable'] for m in meta.values()),'addresses'),
            'ledger_addresses_with_timelines':metric(sum(e['sha256'] is not None for e in inventory),'addresses'),
            'timeline_count':metric(sum(e['sha256'] is not None for e in inventory),'timelines'),
            'trackable_addresses_with_timelines':metric(sum(c['trackable'] and c['timeline_status']!='missing' for c in coverage),'addresses'),
            'unreadable_partial_files':metric(sum(e['status'] in ('unreadable_or_partial','schema_partial') for e in inventory),'timelines'),
            'incomplete_wallet_histories':metric(sum(c.get('history_complete') is False for c in coverage),'addresses'),
            'tornado_excluded':metric(sum(m['tornado'] for m in meta.values()),'addresses'),
            'by_chain':per_chain,'row_quality':dict(qualities),'addresses':coverage},
        'tests':tests,'strata_primary_7d':strata(real,meta),'extreme_cases':extremes,
        'address_results':address_results,
        'interpretation':'Own-history pattern within data checked; never proof of a leak. Placebos and exchangeability failures qualify all pooled p values.',
        'limitations':['Live fetcher snapshot; unavailable chains/partial files are never inactive addresses.',
            'Only native assets and explicit recognised token contracts valued; unrecognised tokens excluded.',
            'Balance turnover requires full recognised-portfolio reconciliation; excluded assets are not zero.',
            'Date-only OFAC publication: announcement-day activity excluded; no intraday advance-notice inference.',
            'Time trends, serial dependence, seizures, indictments, earlier vendor publications and exchange collapses can confound results.',
            'Permutation coupling is a dependence model, not exact inference under arbitrary action/entity time dependence.',
            'OFAC names and identifiers only; destination labels do not establish historical ownership or misconduct.',
            'Coverage append for docs/COVERAGE.md is supplied in PREMOVE.md; shared coverage file not owned.']}
    output['candidate_findings']=candidate_findings(output)
    return output


def candidate_findings(x):
    primary=x['tests']['shift_0_window_7']['pooled']['any_outflow']
    cases=x['extreme_cases']
    meaningful=[c for c in cases if c['tests']['outflow_usd']['real']>c['tests']['outflow_usd']['baseline_max'] and len(c['example_txs'])>=2]
    if not meaningful:meaningful=[c for c in cases if len(c['example_txs'])>=2]
    chosen=[];seen_entities=set()
    for c in sorted(meaningful,key=lambda c:-c['tests']['outflow_usd']['real']):
        entity_key=tuple(e['uid'] for e in c['entities'])
        if entity_key in seen_entities:continue
        seen_entities.add(entity_key);chosen.append(c)
        if len(chosen)==3:break
    examples=[c['example_txs'][0] for c in chosen][:3]
    if len(examples)<2:
        examples=[e for c in cases for e in c['example_txs']][:3]
    actual=primary.get('mean_real',{}).get('value')
    baseline=primary.get('mean_baseline',{}).get('value')
    p=primary.get('p_holm_primary_three_metrics')
    placebos={str(s):x['tests'][f'shift_{s}_window_7']['common_cohort']['any_outflow']['p_one_sided'] for s in (60,90,180)}
    findings=[{'id':'population_pre_week','kind':'population_pattern',
        'sentence':('The checked cohort shows an elevated pre-designation activity rank under the registered model.'
                    if p is not None and p<.05 else
                    'The registered primary test does not establish a cohort-wide excess of pre-designation outflow.'),
        'number':primary['observed_active_addresses'] if 'observed_active_addresses' in primary else metric(0,'addresses'),
        'denominator':primary['addresses'],'observed_share':metric(actual,'share'),
        'baseline_share':metric(baseline,'share'),
        'cluster_count':primary['clusters'],'p_holm':p,'placebo_p_common_cohort':placebos,
        'example_txs':examples,'source_url':sorted({a for c in cases for a in c['action_urls']}),
        'raw_ref':'results/premove.json#/address_results',
        'confidence':'Provisional cohort and conditional rank diagnostic; selected examples illustrate observed transfers, not the population estimate. A nonsignificant result does not establish no anticipation. Fake-date tests, time trends, enforcement events and source coverage limit interpretation.'}]
    contexts=csv_rows(ROOT/'data/reference/cases.csv')
    for c in chosen:
        t=c['tests']['outflow_usd']
        context=[{'case_id':r['case_id'],'notes':r['notes'],'source_url':r['source_url'],'raw_ref':r['raw_ref']}
                 for r in contexts if any(r['name'].upper() in e['name'].upper() for e in c['entities'])]
        findings.append({'id':'case_'+c['chain']+'_'+c['address'],'kind':'exploratory_individual_case',
            'sentence':'; '.join(e['name'] for e in c['entities'])+' had a large outward transfer-time value in the last checked week before its identifier was published.',
            'address':c['address'],'chain':c['chain'],'entities':c['entities'],
            'number':metric(t['real'],'usd','at each constituent transfer time'),
            'baseline_mean':metric(t['baseline_mean'],'usd','at each constituent baseline transfer time'),
            'baseline_max':metric(t['baseline_max'],'usd','at each constituent baseline transfer time'),
            'baseline_active_share':metric(c['tests'].get('any_outflow',{}).get('baseline_mean'),'share'),
            'baseline_windows':c['baseline_windows'],'individual_upper_tail_p':t['upper_tail_p'],
            'example_txs':c['example_txs'],'source_url':c['action_urls'],'raw_ref':c['raw_ref'],
            'context':context,
            'short_window_usd':{str(w):next((r['real']['outflow_usd'] for r in x['address_results'] if r['id']==c['id'] and r['shift_days']==0 and r['window_days']==w),None) for w in (1,3)},
            'placebo_individual_usd_p':{str(sh):next((r['tests'].get('outflow_usd',{}).get('upper_tail_p') for r in x['address_results'] if r['id']==c['id'] and r['shift_days']==sh and r['window_days']==7),None) for sh in (60,90,180)},
            'confidence':'Exploratory selection, no individual multiplicity correction. Timestamped transfers and source prices are evidence for movement; neither their size nor their timing establishes a leak, intent, historical recipient control or unlawful conduct.'})
    # Exploratory follow-up of the highest-ranked sparse Bitcoin cases. This
    # is one entity-level description, not three independent discoveries.
    group=[c for c in cases if c['chain']=='BTC' and any(e['name']=='GRIMM, Matthew Simon' for e in c['entities'])]
    if len(group)>=2:
        ids={c['id'] for c in group}
        rows=[r for r in x['address_results'] if r['id'] in ids and r['shift_days']==0 and r['window_days']==7]
        aligned=len({r['baseline_series']['first_end_utc'] for r in rows})==1
        if aligned:
            n=min(r['baseline_windows'] for r in rows)
            historical=[sum(r['baseline_series']['columns']['outflow_usd'][i] for r in rows) for i in range(n)]
            value=sum(r['tests']['outflow_usd']['real'] for r in rows)
            txs=list({e['hash']:e for c in group for e in c['example_txs']}.values())
            findings.append({'id':'grimm_sparse_case','kind':'exploratory_entity_case',
                'sentence':'Several BTC addresses listed under GRIMM, Matthew Simon moved funds close together before the identifier-publication date; these are one entity-level case.',
                'number':metric(value,'usd','at each constituent transfer time; gross address outflow volume'),
                'addresses':metric(len(rows),'addresses'),'entities':metric(1,'entities'),
                'distinct_example_transactions':metric(len(txs),'transactions'),
                'baseline_mean':metric(statistics.mean(historical),'usd','at each constituent baseline transfer time'),
                'baseline_max':metric(max(historical),'usd','at each constituent baseline transfer time'),
                'baseline_windows':metric(n,'matched windows'),
                'individual_upper_tail_p':(1+sum(v>=value for v in historical))/(n+1),
                'example_txs':txs[:3],'source_url':group[0]['action_urls'],
                'raw_ref':[c['raw_ref'] for c in group],'action_evidence':group[0]['action_evidence'],
                'confidence':'Exploratory follow-up after ranking, not a registered primary entity test. Baselines are aligned to the same weekly endpoints and common history, rather than summing unequal lifetime means. Gross address outflow volume is not unique wealth. Common OFAC entity/action means this is one dependent case; the transactions do not establish notice, controller identity or a leak.'})
    return findings


def fmt(x):
    return 'unavailable' if x is None else f'{x:,.4g}'


def report(x):
    c=x['coverage'];t=x['tests']['shift_0_window_7']
    lines=[MARKER,'',f"Provisional snapshot: {x['generated_at_utc']}. `provisional:true`; fetchers are still running.",'',
       f"Population: {c['ledger_addresses']['value']:,} listed chain–address pairs; {c['trackable_addresses']['value']:,} trackable, {c['untrackable_addresses']['value']:,} untrackable. {c['ledger_addresses_with_timelines']['value']:,} ledger pairs have timeline files (including coverage stubs and excluded Tornado rows); {c['unreadable_partial_files']['value']} unreadable/partial files. {c['tornado_excluded']['value']} Tornado-associated pairs are excluded from wallet statistics.",'',
       f"The primary 7-day test has **{t['eligible_addresses']['value']} eligible wallet addresses**, of which **{t['inactive_addresses']['value']} have no recognised non-dust outflow in any tested real/baseline window**. Inactivity is within the checked assets and time windows, not a statement that the address never transacted.",'',
       '### Actual versus own historical weeks','',
       '| Metric | Addresses | Connected clusters | Real mean | Baseline mean | Cluster rank score | One-sided p | Holm p |',
       '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    findings_lines=['','### Candidate findings to review','']
    for finding in x['candidate_findings']:
        findings_lines.extend([finding['sentence'],''])
        n=finding['number']
        if finding['kind']=='population_pattern':
            findings_lines.append(f"**{n['value']} addresses of {finding['denominator']['value']} eligible addresses** had pre-week non-dust outflow; observed address share {fmt(finding['observed_share']['value'])}, mean own-baseline weekly share {fmt(finding['baseline_share']['value'])}. {finding['cluster_count']['value']} connected action/entity clusters; Holm p={fmt(finding['p_holm'])}. Common-cohort fake-date binary p values: {finding['placebo_p_common_cohort']}.")
        elif finding['kind']=='exploratory_individual_case':
            findings_lines.append(f"**USD {n['value']:,.2f}, valued at each transfer time**; own-baseline weekly mean USD {finding['baseline_mean']['value']:,.2f}, maximum USD {finding['baseline_max']['value']:,.2f}; {finding['baseline_windows']['value']} baseline weeks, active fraction {fmt(finding['baseline_active_share']['value'])}. Individual upper-tail p={fmt(finding['individual_upper_tail_p'])}.")
        else:
            findings_lines.append(f"**USD {n['value']:,.2f} gross address outflow volume, valued at each transfer time**, from {finding['addresses']['value']} addresses under {finding['entities']['value']} OFAC entity; {finding['distinct_example_transactions']['value']} distinct example transactions. Matched-baseline weekly mean USD {finding['baseline_mean']['value']:,.2f}, maximum USD {finding['baseline_max']['value']:,.2f}, {finding['baseline_windows']['value']} common weeks; exploratory upper-tail p={fmt(finding['individual_upper_tail_p'])}.")
        if finding['kind']=='exploratory_individual_case':
            findings_lines.extend(['',f"Shorter-window outward USD at transfer times: { {k:(v['value'] if v else None) for k,v in finding['short_window_usd'].items()} }. Individual fake-date USD upper-tail p values: {finding['placebo_individual_usd_p']}. Small fake-date p values weaken an anticipation interpretation for this case."])
        findings_lines.extend(['',finding['confidence'],''])
        for e in finding['example_txs']:
            findings_lines.append(f"- [{e['hash']}]({e['explorer_url']}) ({e['chain']}, {e['time_utc']}); USD {e['outflow_usd']['value']:,.2f} at transfer time; price observation {e['price']['valued_at']}.")
        for context in finding.get('context',[]):
            findings_lines.extend(['',f"Saved context: {context['notes']} [Source]({context['source_url']}); `{context['raw_ref']}`."])
        findings_lines.append('')
    # Insert before the table heading, whose header rows are already in lines.
    where=lines.index('### Actual versus own historical weeks')
    lines[where:where]=findings_lines
    for k,v in t['pooled'].items():
        lines.append('| '+ ' | '.join([k,str(v['addresses']['value']),str(v['clusters']['value']),fmt(v.get('mean_real',{}).get('value')),fmt(v.get('mean_baseline',{}).get('value')),fmt(v.get('cluster_equal_weight_centered_midrank',{}).get('value')),fmt(v['p_one_sided']),fmt(v.get('p_holm_primary_three_metrics'))])+' |')
    lines+=['','USD means are USD per address-window at each transfer time; binary means are address shares, turnover means are unbounded gross outflow/opening balance ratios, not fractions of wealth removed. Tiny positive opening balances plus replenishment can make their arithmetic means enormous; use the registered ranks rather than these unstable magnitudes. Cluster score zero is the permutation center. Missing balance or price metrics are unavailable, not zero. P values are conditional diagnostics under the registered dependence model. Strata and cases are exploratory.','',
            '### Fake designation dates and shorter windows','',
            '| Shift before actual T (days) | Window (days) | Eligible addresses | Inactive addresses | Binary p | USD p | Balance p |',
            '| ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in (0,60,90,180):
        for w in (7,3,1):
            v=x['tests'][f'shift_{s}_window_{w}'];p=v['pooled']
            lines.append(f"| {s} | {w} | {v['eligible_addresses']['value']} | {v['inactive_addresses']['value']} | {fmt(p['any_outflow']['p_one_sided'])} | {fmt(p['outflow_usd']['p_one_sided'])} | {fmt(p['balance_turnover']['p_one_sided'])} |")
    lines+=['','Common-address placebo cohorts, active-history-only results, action-only/entity-only partitions and results excluding >10,000-transaction addresses are in `results/premove.json`. Program membership overlaps. Connected action/entity clustering is the primary analysis.','',
            '### Chain coverage','',
            '| Chain | Listed addresses | Trackable | Files/stubs | Readable wallet files | Complete wallet histories | Eligible 7-day |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in c['by_chain']:
        lines.append('| '+' | '.join([row['chain']]+[str(row[k]['value']) for k in ('ledger_addresses','trackable_addresses','with_timeline','readable_wallet_timelines','complete_wallet_histories','eligible_primary')])+' |')
    lines+=['','Chain-level details and per-address missing ranges/notes/reconciliation are retained in JSON. Full-history requirements exclude partial cohorts from inference even if a recent event window was fetched. Untrackable/private chains remain in the population table. No outflow found means within saved data checked.','',
            '### Most extreme individual cases','',
            'Sorted by the registered conservative individual upper-tail p, then descending transfer-time USD. This selection has no individual-discovery error correction and does not identify advance knowledge. Each case links OFAC action evidence, a complete baseline and example raw transactions in the JSON.']
    for i,case in enumerate(x['extreme_cases'],1):
        test=case['tests']['outflow_usd'];names='; '.join(e['name'] for e in case['entities'])
        lines+=['',f"{i}. **{names}** — {case['chain']} `{case['address']}`, listed {case['listed_date']}. Seven-day outward value **USD {test['real']:,.2f} at each transfer time**; baseline mean USD {test['baseline_mean']:,.2f}, median USD {test['baseline_median']:,.2f}, maximum USD {test['baseline_max']:,.2f} per prior week ({case['baseline_windows']['value']} weeks). Midrank {test['midrank']:.4f}, conservative individual p={test['upper_tail_p']:.4g}." ]
        for e in case['example_txs']:
            lines.append(f"   - [{e['hash']}]({e['explorer_url']}) — {e['amount']['value']} {e['symbol']}, USD {e['outflow_usd']['value']:,.2f} at transfer {e['time_utc']}; price observed {e['price']['valued_at']}. Raw: `{e['raw_ref']}`.")
    lines+=['','### Interpretation, prior work and limitations','',
            'A higher pre-designation rank is a descriptive timing pattern, never proof of a leak. Seizures, indictments, earlier vendor reports, market regimes, service growth/decline, exchange failures and ordinary treasury sweeps can produce the same pattern. Saved `data/reference/cases.csv` and `vendor_claims.csv` provide context but cannot establish advance knowledge for a selected transaction. Historical recipient labels are unverified unless their validity dates are independently sourced.','',
            'The contribution beyond the saved Ethereum/Bitcoin prior art is the registered own-address weekly control with explicit 30-day buffer, clustered rank diagnostic, three fake-date checks, multi-chain source population and priced/coverage-aware abstention. Prior art already covers announcement anticipation; no claim of first discovery is made (see `docs/PRIOR_ART.md`).','',
            'Implementation note: turnover uses unit `ratio`, extending the results schema because the site contract reserves `share` for 0–1 fractions. Wrapped ETH/BTC use the ETH/BTC price proxy; wrapped-asset basis risk is not measured. These are encoding/valuation qualifications, not changes to the registered windows or tests.','',
            'The actual and fake-date cohorts can differ. The JSON includes a common-ID cohort; metric availability may still differ because a zero opening balance has no turnover denominator. A significant fake-date result weakens a pre-announcement interpretation. Common shocks and time dependence prevent exact causal inference even after action/entity clustering.','',
            'Balance share is deliberately strict: every recognised asset in a portfolio must have a nonnegative accounting path and a compatible independent ending balance. Missing fees, staking/rent adjustments, issuer burns or state snapshots at different blocks can suppress this metric. Native-coin UTXO outflow follows the fetcher’s net-debit/change convention, not the gross value of all transaction outputs; multisender fees are allocated by that source convention. Tron confirmed token events may lack block numbers; confirmation is supplied by the API route. XRP balance-change rows can include non-payment ledger operations.','',
            'Operational notes: standard-library implementation, offline price/label helpers only; no dependency installation or network access. Reviewed local helper imports and interpreter startup configuration; this constrained execution scope is not a global repository security claim. The analysis outputs are retained; atomic JSON saves use a short-lived `premove.json.*` sibling in results. ','',
            '### Reproduce','',
            '```sh','.venv/bin/python scripts/analysis/premove.py --self-test','.venv/bin/python scripts/analysis/premove.py','.venv/bin/python scripts/analysis/premove.py --check','```','',
            '`--check` verifies hashes and recomputes the saved timeline inventory. It fails on a changed/missing/arrived input rather than silently adopting a live fetcher update. Regeneration adopts new histories without changing the script. JSON includes baseline windows, raw refs, price observations for case examples, and exclusions for every horizon/placebo.','',
            'This is research, not legal or compliance advice.']
    return '\n'.join(lines)+'\n'


def self_test():
    assert rank_values([0,0,0])==[.5,.5,.5]
    assert rank_values([0,0,1])==[1/3,1/3,5/6]
    fake=[{'id':'a'},{'id':'b'},{'id':'c'}]
    metas={'a':{'action_urls':['x'],'entity_uids':['1']},'b':{'action_urls':['x'],'entity_uids':['2']},'c':{'action_urls':['y'],'entity_uids':['2']}}
    assert len(components(fake,metas))==1
    assert len(components(fake,metas,'action'))==2
    assert timestamp('2022-08-08T00:00:00-04:00')==timestamp('2022-08-08T04:00:00Z')
    assert asset_info('ETH',{'asset':'0xdead','symbol':'USDT','decimals':6}) is None
    assert asset_info('ETH',{'asset':'0xdac17f958d2ee523a2206206994597c13d831ec7','decimals':18}) is None
    h=History.__new__(History);h.balance_usable=False
    h.outgoing=[{'ts':1,'usd':2},{'ts':2,'usd':None},{'ts':3,'usd':5}];h.out_times=[1,2,3]
    assert h.window(1,2)['outflow_usd']==2
    assert h.window(2,3)['any_outflow'] is None
    assert h.window(3,4)['outflow_usd']==5
    assert h.window(4,5)['any_outflow']==0
    try:gzip.decompress(b'partial')
    except (OSError,EOFError,zlib.error):pass
    else:raise AssertionError('corrupt gzip accepted')
    from unittest.mock import patch
    def tx(k,d,a,fee='0',success=True):
        return {'hash':str(k),'block':k,'time_utc':f'2020-01-0{k}T00:00:00Z',
                'direction':d,'asset':'BTC','amount':a,'fee':fee,'raw_ref':'synthetic','success':success}
    x={'chain':'BTC','address':'synthetic','txs':[tx(1,'in','100'),tx(2,'out','10','1'),
        tx(3,'self','0','1'),tx(4,'out','50','1',False)],
        'coverage':{'complete':True,'to_block':4,'to_time':'2020-01-05T00:00:00Z'},
        'balance_now':[{'asset':'BTC','amount':'87','block':4,'raw_ref':'synthetic'}]}
    q={'price':1,'valued_at':'synthetic','source':'synthetic','raw_ref':'synthetic','source_url':'synthetic'}
    with patch(__name__+'.quote',return_value=q):
        hist=History('BTC',x)
        assert hist.balance_usable and len(hist.outgoing)==1
        assert hist.reconciliation[0]['reconstructed']=='87'
        assert hist.window(timestamp('2020-01-02T00:00:00Z'),timestamp('2020-01-03T00:00:00Z'))['balance_turnover']==.1
        partial={**x,'coverage':{**x['coverage'],'complete':False}}
        assert evaluate(History('BTC',partial),{'listed_date':'2020-12-01'},0,7)[1]=='incomplete_or_malformed_history'
    with tempfile.TemporaryDirectory(prefix='premove-test-') as temp:
        f=Path(temp)/'broken.json.gz';f.write_bytes(b'broken')
        assert read_timeline(f)[1]['status']=='unreadable_or_partial'
        f.write_bytes(gzip.compress(json.dumps({'coverage':{},'txs':[]}).encode()))
        assert read_timeline(f)[1]['status']=='unreadable_or_partial'
    def test_row(values):
        ranks=rank_values(values)
        return {'id':'a','tests':{'any_outflow':{'midrank':ranks[-1],'real':values[-1],
            'baseline_mean':sum(values[:-1])/len(values[:-1])}},'_samples':{'any_outflow':ranks},
            'real':{'any_outflow':{'value':values[-1]}}}
    meta={'a':{'action_urls':['x'],'entity_uids':['1']}}
    assert pooled([test_row([0]*13)],meta,'any_outflow',draws=999)['p_one_sided']==1
    assert abs(pooled([test_row([0]*12+[1])],meta,'any_outflow',draws=999)['p_one_sided']-1/13)<.04
    print('self-test passed: ties, transitive clusters, ET clock, allowlist, boundaries, missing prices, corrupt/partial files, fee/self/failed accounting, reconciliation, turnover, incomplete exclusion and rank nulls')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check',action='store_true')
    ap.add_argument('--self-test',action='store_true')
    args=ap.parse_args()
    if args.self_test:self_test();return 0
    saved=json.loads(OUT.read_text()) if args.check else None
    x=run(saved)
    from scripts.lib.fetch_status import apply_status, report_status
    x=apply_status(x,ROOT,"premove")
    if saved:
        if x!=saved:
            changed=[k for k in x if x[k]!=saved.get(k)]
            print('recomputation differs: '+', '.join(changed),file=sys.stderr);return 1
        print('check passed: input hashes, frozen timeline inventory and all results reproduced');return 0
    if x['inputs_changed_during_run']:
        raise RuntimeError('inputs changed while running; rerun: '+', '.join(x['inputs_changed_during_run']))
    # A short-lived analysis-specific sibling permits atomic replacement within
    # the results filesystem; it is removed on success or failure.
    with io.StringIO() as f:
        json.dump(x,f,separators=(',',':'),allow_nan=False)
        payload=f.getvalue()+'\n'
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=OUT.parent,prefix='premove.json.',delete=False) as tmp:
        tmp.write(payload);tmp_path=Path(tmp.name)
    try:os.replace(tmp_path,OUT)
    finally:tmp_path.unlink(missing_ok=True)
    old=DOC.read_text();design=old.split(MARKER)[0]
    DOC.write_text(design+report_status(report(x),x))
    print(json.dumps({'provisional':x['provisional'],'timeline_count':x['coverage']['timeline_count'],
                      'eligible_primary':x['tests']['shift_0_window_7']['eligible_addresses'],
                      'extreme_cases':len(x['extreme_cases'])}))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(1)
