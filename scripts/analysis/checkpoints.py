#!/usr/bin/env python3
"""Offline checkpoint analysis. Rerunnable while fetchers write; see CHECKPOINTS.md."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True
import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zlib
import bisect
import io
import math
import statistics
from decimal import Decimal, InvalidOperation, getcontext
from functools import lru_cache
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'results/checkpoints.json'
CSV = ROOT / 'data/derived/address_summary.csv'
DOC = ROOT / 'docs/analysis/CHECKPOINTS.md'
EVM = {'ETH', 'ARB', 'BSC', 'ETC', 'OP', 'BASE', 'POLYGON', 'AVAX'}
UTC = dt.timezone.utc
ET = ZoneInfo('America/New_York')
getcontext().prec = 90
NATIVE = {'ETH':'ETH','ARB':'ETH','BSC':'BNB','ETC':'ETC','OP':'ETH','BASE':'ETH',
          'POLYGON':'POL','AVAX':'AVAX','BTC':'BTC','BCH':'BCH','BSV':'BSV','BTG':'BTG',
          'TRX':'TRX','LTC':'LTC','DOGE':'DOGE','DASH':'DASH','ZEC':'ZEC',
          'XVG':'XVG','XRP':'XRP','SOL':'SOL','BNB':'BNB'}
# Identity authorizes valuation, never an explorer-provided ticker. Wrapped-coin
# prices below are explicitly underlying-asset proxies, not redemption claims.
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
 'SOL': {'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v':('USDC',6),
         'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB':('USDT',6)},
}
# Recognise legitimate unpriced assets too: their positive transfers are unknown
# for the $1 rule, rather than misclassifying them as fake-token spam.
TOKENS['ETH'].update({
 '0xa47c8bf37f92abed4a126bda807a7b7498661acd':('UST',18),
 '0x674c6ad92fd080e4004b2312b45f796a192d27a0':('USDN',18),
 '0x5a98fcbea516cf06857215779fd812ca3bef1b32':('LDO',18),
 '0x514910771af9ca656af840dff83e8264ecf986ca':('LINK',18),
 '0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0':('MATIC',18),
 '0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce':('SHIB',18),
 '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984':('UNI',18),
 '0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0':('WSTETH',18),
 '0xae7ab96520de3a18e5e111b5eaab095312d7fe84':('STETH',18),
 '0xd533a949740bb3306d119cc777fa900ba034cd52':('CRV',18),
 '0x04fa0d235c4abf4bcf4787af4cf447de572ef828':('UMA',18),
 '0x408e41876cccdc0f92210600ef50372656052a38':('REN',18),
 '0x77777feddddffc19ff86db637967013e6c6a116c':('TORN',18),
})
TOKENS['TRX']['TEk2J6HjyBKu47ai6ScwkbchfkWnPWuckM']=('TUSD',18)
TOKENS['ARB'].update({'0x82af49447d8a07e3bd95bd0d56f35241523fbab1':('ETH',18),
                      '0x912ce59144191c1204e64559fe8253a0e49e6548':('ARB',18)})
TOKENS['BSC']={'0x55d398326f99059ff775485246999027b3197955':('USDT',18),
               '0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d':('USDC',18)}
sys.path.insert(0, str(ROOT))
from scripts.prices import price as prices


def timestamp(s):
    if not s: return None
    try:
        x = dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return x.replace(tzinfo=x.tzinfo or UTC).timestamp()
    except (ValueError, TypeError, OverflowError): return None


def iso(t):
    return dt.datetime.fromtimestamp(t, UTC).isoformat().replace('+00:00','Z') if t is not None else None


def dec(v):
    try:
        n = Decimal(str(v))
        return n if n.is_finite() and abs(n) < Decimal('1e90') else None
    except (InvalidOperation, ValueError, TypeError): return None


def split(s):
    return [v for v in (s or '').split(';') if v]


def tornado_excluded(r):
    # Match the pre-move analysis' conservative protocol-wide population rule.
    return r['tornado_contract'] or any('TORNADO' in name.upper() for name in r.get('sdn_names',[]))


def identity(chain, row):
    asset = str(row.get('asset') or '')
    if chain in EVM and asset.startswith('0x'): asset = asset.lower()
    if asset == NATIVE.get(chain): return asset, asset
    token = TOKENS.get(chain, {}).get(asset)
    if token and str(row.get('decimals',token[1])) == str(token[1]): return asset, token[0]
    return asset, None


@lru_cache(maxsize=40000)
def quote(symbol, t):
    if symbol is None: return None
    price, observed, source = prices.usd(symbol, iso(t))
    if price is None or not math.isfinite(price) or price <= 0: return None
    resolved = prices.resolve_asset(symbol)
    frequency = '1h' if source.startswith('Binance') else '1d'
    row = prices._lookup_rows(resolved['symbol'], frequency, dt.datetime.fromtimestamp(t, UTC))
    return {'price_usd': price, 'valued_at': observed, 'source': source,
            'raw_ref': row['raw_ref'], 'source_url': row['source_url']}


def explorer(chain, txhash):
    base = {'BTC':'https://mempool.space/tx/','BCH':'https://blockchair.com/bitcoin-cash/transaction/',
            'BSV':'https://whatsonchain.com/tx/','BTG':'https://btgexplorer.com/tx/',
            'LTC':'https://litecoinspace.org/tx/','DOGE':'https://dogechain.info/tx/',
            'DASH':'https://explorer.dash.org/insight/tx/','ETH':'https://etherscan.io/tx/',
            'ARB':'https://arbiscan.io/tx/','BSC':'https://bscscan.com/tx/',
            'ETC':'https://etc.blockscout.com/tx/','OP':'https://optimistic.etherscan.io/tx/',
            'BASE':'https://basescan.org/tx/','POLYGON':'https://polygonscan.com/tx/',
            'AVAX':'https://snowtrace.io/tx/','TRX':'https://tronscan.org/#/transaction/',
            'SOL':'https://solscan.io/tx/','XRP':'https://livenet.xrpl.org/transactions/',
            'BNB':'https://explorer.bnbchain.org/tx/'}
    return base[chain]+txhash if chain in base else None


def event_evidence(chain, tx, i, symbol, usd, q):
    return {'chain':chain, 'hash':tx['hash'], 'explorer_url':explorer(chain,tx['hash']),
            'time_utc':tx['time_utc'], 'asset':tx['asset'], 'symbol':symbol,
            'amount':metric(tx['amount'],'native:'+str(tx['asset'])),
            'usd':metric(usd,'usd',tx['time_utc']), 'price':q,
            'raw_ref':tx['raw_ref'], 'timeline_row':i}


def blank_summary(meta, other=False):
    chain = meta['chain'].upper()
    return {'chain':chain, 'address':meta['address_normalized'],
            'view':'same_address_other_evm_chain' if other else 'listed_chain',
            'listed_date':meta['first_listed_date'], 'sdn_uids':split(meta.get('sdn_uids') or meta.get('all_entity_uids')),
            'programs':split(meta['programs']), 'trackable':meta['trackable'].lower()=='true',
            'untrackable_reason':meta.get('untrackable_reason'), 'raw_ref':meta.get('raw_ref'),
            'source_url':meta.get('source_url'), 'timeline':None, 'history_complete':False,
            'exchange_scale':None, 'tornado_contract':meta.get('_tornado',False),
            'balance_at_designation_usd':None, 'still_there_today_usd':None,
            'moved_after':None, 'moved_before':None, 'received_after':None,
            'first_outflow_lag_days':None, 'last_outflow_before_lag_days':None,
            'total_inflow_after_usd':None, 'priced_inflow_after_subtotal_usd':None,
            'share_T_balance_gone':{k:None for k in ['T+7d','T+30d','T+365d','today']},
            'checkpoints':{}, 'examples':{}, 'quality':{}, 'reconciliation':[]}


def analyze(x, meta, path, other=False):
    r = blank_summary(meta, other)
    chain = r['chain']; cov = x['coverage']; r['timeline'] = rel(path)
    r['raw_ref'] = rel(path)
    r['tornado_contract'] = r['tornado_contract'] or bool(x.get('tornado_pool'))
    Tlocal = dt.datetime.fromisoformat(meta['first_listed_date']).replace(tzinfo=ET)
    T = Tlocal.timestamp(); pub = Tlocal.replace(hour=12).timestamp()
    end = timestamp(cov.get('checked_through_time') or cov.get('to_time') or x.get('fetched_at'))
    if chain in {'SOL','XRP','BNB'}: end = timestamp(x.get('fetched_at')) or end
    r['checked_through_utc'] = iso(end)
    r['T_pub_interval_utc'] = [iso(T),iso((Tlocal+dt.timedelta(days=1)).timestamp()-1)]
    targets = {'T-7d':(Tlocal-dt.timedelta(days=7)).timestamp(),'T':T,
               **{'T+'+str(d)+'d':(Tlocal+dt.timedelta(days=d)).timestamp() for d in (7,30,365)}, 'today':end}
    deltas = collections.defaultdict(lambda:collections.defaultdict(Decimal))
    symbols = {NATIVE[chain]:NATIVE[chain]} if chain in NATIVE else {}
    bad = set(); quality = collections.Counter(); hashes = set()
    events = {'before':[],'after':[],'in':[]}; unknown = collections.Counter()
    inflow = 0.; inflow_dust = 0.; largest_in = []; largest_out = []; last_before = None; funding_candidates={}
    for i, tx in enumerate(x['txs']):
        if not isinstance(tx,dict): quality['malformed_rows']+=1; continue
        if tx.get('confirmed') is False or (not tx.get('block') and chain != 'TRX'):
            quality['unconfirmed_rows']+=1; continue
        t = timestamp(tx.get('time_utc'))
        if t is None: quality['undated_rows']+=1; continue
        amount = dec(tx.get('amount')); direction = tx.get('direction'); asset, symbol = identity(chain,tx)
        if amount is None or amount < 0 or direction not in {'in','out','self'} or not tx.get('hash') or not tx.get('raw_ref') or not asset:
            quality['malformed_rows']+=1; continue
        hashes.add(tx['hash']); symbols[asset] = symbol
        if tx.get('decimals_known') is False: bad.add(asset)
        fee_asset = str(tx.get('fee_asset') or NATIVE.get(chain) or asset)
        fee = dec(tx.get('fee'))
        if fee is None: bad.add(fee_asset); fee = Decimal(0)
        if fee > 0:
            deltas[fee_asset][t] -= fee
            symbols[fee_asset] = NATIVE.get(chain) if fee_asset == NATIVE.get(chain) else None
        success = tx.get('success',True) is not False and str(tx.get('status','')).lower() not in {'failed','failure','reverted'}
        if not success: continue
        delta = amount if direction=='in' else -amount if direction=='out' else Decimal(0)
        deltas[asset][t] += delta
        if amount == 0 or direction=='self' or tx.get('is_transfer',True) is False: continue
        window = 'before' if targets['T-7d'] <= t < T and direction=='out' else 'after' if t>=T and direction=='out' else 'in' if t>=T and direction=='in' else None
        # Unknown contract identity is excluded from genuine-payment claims.
        if symbol is None:
            quality['unrecognised_asset_transfer_rows']+=1
            if window: quality['excluded_unknown_'+window+'_rows']+=1
            continue
        if direction=='in' and (asset not in funding_candidates or amount>funding_candidates[asset][0]):
            funding_candidates[asset]=(amount,i,tx,symbol,t)
        if window is None and not (t<T and direction=='out'): continue
        q = quote(symbol,t); value = float(amount)*q['price_usd'] if q else None
        if value is None:
            if window: unknown[window]+=1
            continue
        if value < 1:
            if window: quality['dust_'+window+'_rows']+=1
            if window=='in': inflow_dust += value
            continue
        ev = None
        if t<T and direction=='out' and (last_before is None or t>last_before[0]):
            ev=event_evidence(chain,tx,i,symbol,value,q); last_before=(t,ev)
        if window:
            ev=ev or event_evidence(chain,tx,i,symbol,value,q)
            if window=='in':
                inflow+=value
                largest_in.append((value,i,ev)); largest_in=sorted(largest_in,reverse=True)[:3]
            else:
                events[window].append((t,i,ev))
                events[window]=sorted(events[window])[:3]
                if window=='after':
                    largest_out.append((value,i,ev)); largest_out=sorted(largest_out,reverse=True)[:3]
    complete = cov.get('complete') is True and not quality['malformed_rows'] and not quality['undated_rows']
    r['history_complete'] = complete
    r['exchange_scale'] = len(hashes)>10000 or cov.get('huge_address',False) or int(cov.get('reported_history_records') or 0)>10000
    r['transaction_count'] = len(hashes)
    for k in ['before','after']:
        events[k].sort()
        r['moved_'+k] = True if events[k] else False if complete and not unknown[k] else None
    r['received_after'] = True if largest_in else False if complete and not unknown['in'] else None
    if events['after']: r['first_outflow_lag_days'] = (events['after'][0][0]-pub)/86400
    r['first_outflow_exact_within_checked_history'] = complete and not unknown['after']
    if last_before: r['last_outflow_before_lag_days'] = (last_before[0]-pub)/86400
    r['examples'] = {'first_outflow':events['after'][0][2] if events['after'] else None,
                     'last_outflow_before':last_before[1] if last_before else None,
                     'largest_outflows':[e[2] for e in largest_out], 'largest_inflows':[e[2] for e in largest_in]}
    funding=[]
    for amount,i,tx,symbol,t in funding_candidates.values():
        q=quote(symbol,t)
        if q and float(amount)*q['price_usd']>=1:
            funding.append(event_evidence(chain,tx,i,symbol,float(amount)*q['price_usd'],q))
    r['examples']['funding_any_time']=sorted(funding,key=lambda e:e['usd']['value'],reverse=True)[:3]
    r['priced_inflow_after_subtotal_usd'] = inflow
    r['total_inflow_after_usd'] = inflow if complete and not unknown['in'] else None
    r['dust_inflow_after_subtotal_usd'] = inflow_dust
    r['unpriced_recognised_transfer_rows'] = dict(unknown)
    observed = {}
    for b in x.get('balance_now',[]):
        if not isinstance(b,dict): continue
        asset,symbol = identity(chain,b); amount = dec(b.get('amount'))
        if asset and amount is not None and amount>=0 and b.get('raw_ref'):
            observed[asset]=b; symbols[asset]=symbol
    streams = {}
    for asset in sorted(symbols):
        cumulative=[]; times=[]; total=Decimal(0); minimum=Decimal(0)
        for t,v in sorted(deltas[asset].items()):
            total+=v; minimum=min(minimum,total); times.append(t); cumulative.append(total)
        b=observed.get(asset); amount=dec(b['amount']) if b else None
        # EVM snapshots must be at the history head. Other fetchers explicitly
        # use asynchronous latest observations; equality is necessary, not an
        # independent proof that their indexer retained every event.
        compatible = bool(b)
        if chain in EVM and b and b.get('block') and cov.get('to_block'):
            compatible = int(b['block']) == int(cov['to_block'])
        tolerance=Decimal('1e-8') if chain in {'BTC','BCH','BSV','BTG','LTC','DOGE','DASH','ZEC','XVG'} else Decimal('1e-12')
        good = compatible and amount is not None and abs(total-amount)<=tolerance and minimum>=-tolerance and asset not in bad
        usable=complete and good
        streams[asset]=(times,cumulative,usable)
        r['reconciliation'].append({'asset':asset,'symbol':symbols[asset], 'reconstructed_native':str(total),
            'observed_native':str(amount) if amount is not None else None,'minimum_native':str(minimum),
            'pass':bool(good),'historical_usable':bool(usable),'same_history_block':compatible,
            'raw_ref':b.get('raw_ref') if b else None})
    for name,t in targets.items():
        assets=[]; priced_subtotal=0.; missing=0; known=0; unrecognised_positive=0
        for asset in sorted(symbols):
            times,values,usable=streams[asset]; b=observed.get(asset)
            amount=None; source='unavailable'; raw=None
            bt=timestamp(b.get('as_of') or b.get('reported_at')) if b else None
            bt=bt or timestamp(x.get('balance_observation',{}).get('time_utc')) or end
            valuation_time=bt if name=='today' else t
            if name=='today' and b:
                amount=dec(b['amount']); source='observed'; raw=b['raw_ref']
            elif usable and t is not None and end is not None and t<=end:
                k=bisect.bisect_left(times,t)-1
                amount=max(Decimal(0),values[k] if k>=0 else Decimal(0)); source='reconciled_transfer_history'; raw=rel(path)+'#txs'
            q=quote(symbols[asset],valuation_time) if valuation_time is not None and symbols[asset] else None
            usd=float(amount)*q['price_usd'] if amount is not None and q else 0. if amount==0 and symbols[asset] else None
            if symbols[asset]:
                if usd is not None: priced_subtotal+=usd; known+=1
                else: missing+=1
            elif amount is not None and amount>0: unrecognised_positive+=1
            assets.append({'asset':asset, 'symbol':symbols[asset], 'native':str(amount) if amount is not None else None,
                           'usd':usd, 'valued_at':iso(valuation_time), 'price':q, 'method':source,'raw_ref':raw})
        total=priced_subtotal if known and missing==0 else None
        r['checkpoints'][name]={'time_utc':iso(t), 'assets':assets, 'recognised_assets_usd':metric(total,'usd',iso(t) or 'unavailable'),
              'priced_subtotal_usd':metric(priced_subtotal if known else None,'usd',iso(t) or 'unavailable'),
              'unavailable_recognised_assets':missing, 'unrecognised_positive_balances':unrecognised_positive}
    r['balance_at_designation_usd']=r['checkpoints']['T']['recognised_assets_usd']['value']
    r['still_there_today_usd']=r['checkpoints']['today']['recognised_assets_usd']['value']
    initial={a['asset']:a for a in r['checkpoints']['T']['assets'] if a['symbol']}
    for name in r['share_T_balance_gone']:
        now={a['asset']:a for a in r['checkpoints'][name]['assets']}
        denominator=0.; depleted=0.; valid=True
        for asset,a in initial.items():
            if a['native'] is None: valid=False; break
            amount=Decimal(a['native'])
            if amount==0: continue
            later=now[asset]
            if later['native'] is None or a['price'] is None: valid=False; break
            denominator+=float(amount)*a['price']['price_usd']
            depleted+=float(max(Decimal(0),amount-Decimal(later['native'])))*a['price']['price_usd']
        if valid and denominator>0:
            r['share_T_balance_gone'][name]=min(1.,depleted/denominator)
    r['quality']=dict(quality)
    return r


def rows(p):
    with p.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def rel(p):
    return p.resolve().relative_to(ROOT).as_posix()


def metric(value, unit, valued_at=None):
    return dict(value=value, unit=unit, **({'valued_at': valued_at} if valued_at else {}))


def norm(chain, a):
    return a.lower() if chain in EVM or a.lower().startswith('bc1') else a


def read_timeline(p):
    entry = {'path': rel(p)}
    try:
        b = p.read_bytes()
        entry['sha256'] = hashlib.sha256(b).hexdigest()
        x = json.loads(gzip.decompress(b) if p.suffix == '.gz' else b)
        if not (isinstance(x, dict) and isinstance(x.get('txs'), list)
                and isinstance(x.get('coverage'), dict)
                and isinstance(x.get('balance_now', []), list)
                and isinstance(x.get('chain'), str) and isinstance(x.get('address'), str)):
            raise ValueError('required timeline schema absent')
        entry['status'] = 'readable'
        return x, entry
    except (OSError, ValueError, EOFError, UnicodeError, zlib.error) as e:
        entry.update(status='unreadable_or_partial', error=type(e).__name__)
        return None, entry


def atomic(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=p.parent, prefix=p.name+'.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        os.replace(name, p)
    finally:
        if os.path.exists(name): os.unlink(name)


def load(stage='loader', save_progress=True, snapshot=None):
    address_rows = rows(ROOT / 'data/addresses.csv')
    index = {(r['chain'].upper(), norm(r['chain'].upper(), r['address_normalized'])): r for r in address_rows}
    ledger=rows(ROOT/'data/ledger.csv')
    names={r['sdn_uid']:r['sdn_name'] for r in ledger}
    # Public labels identify protocol roles only; never infer a controller.
    with (ROOT/'data/labels/labels.csv').open(newline='',encoding='utf-8-sig') as f:
        for label in csv.DictReader(f):
            key=(label['chain'],label['address_normalized'])
            if key in index and label['class']=='mixer' and 'tornado' in label['label'].lower():
                index[key]['_tornado']=True
    by_string={}
    for (chain,a),meta in index.items():
        if chain in EVM and (a not in by_string or meta['first_listed_date']<by_string[a]['first_listed_date']): by_string[a]=meta
    manifest, found, extras = [], set(), 0
    summaries={}; same_address=[]; seen=set()
    paths=[ROOT/m['path'] for m in snapshot['timeline_manifest']] if snapshot else sorted((ROOT / 'data/timelines').glob('*/*.json*'))
    for n,p in enumerate(paths):
        if not (p.name.endswith('.json') or p.name.endswith('.json.gz')): continue
        x, entry = read_timeline(p)
        manifest.append(entry)
        if x is None: continue
        key = (x['chain'].upper(), norm(x['chain'].upper(), x['address']))
        if key in seen:
            entry['status']='duplicate_chain_address_skipped'; continue
        seen.add(key)
        if key in index:
            found.add(key)
            if stage!='loader':
                try: summaries[key]=analyze(x,index[key],p)
                except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as e:
                    entry.update(status='unusable_partial_schema',error=type(e).__name__)
        else:
            extras += 1
            if stage!='loader' and key[0] in EVM and key[1] in by_string:
                meta=dict(by_string[key[1]],chain=key[0])
                try: same_address.append(analyze(x,meta,p,True))
                except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as e:
                    entry.update(status='unusable_partial_schema',error=type(e).__name__)
        if n%100==0: print(f'{stage}: {n+1}/{len(paths)} timeline files processed',flush=True)
        if save_progress and stage!='loader' and n>0 and n%200==0:
            partial_rows=[summaries.get(k) or blank_summary(m) for k,m in sorted(index.items())]
            for r in partial_rows+same_address: r['sdn_names']=[names.get(uid,uid) for uid in r['sdn_uids']]
            partial={'schema_version':1,'provisional':True,'stage':'balances_in_progress',
                'processing_complete':False,'generated_at_utc':dt.datetime.now(UTC).isoformat(),
                'script':rel(Path(__file__)),'addresses':partial_rows,'same_address_other_evm_chain':list(same_address),
                'coverage':{'ledger_addresses':metric(len(index),'addresses'),
                            'ledger_addresses_with_readable_timelines':metric(len(found),'addresses'),
                            'timeline_files_processed':metric(n+1,'files')},'timeline_manifest':list(manifest)}
            text=csv_text(partial)
            partial['address_summary_sha256']=hashlib.sha256(text.encode()).hexdigest()
            atomic(CSV,text)
            atomic(OUT,json.dumps(compact_result(partial),separators=(',',':'),allow_nan=False)+'\n')
            print(f'Partial balances saved: {len(summaries)} listed addresses; CSV {len(text.encode())/1048576:.2f} MiB',flush=True)
        del x
    result = {'schema_version': 1, 'provisional': True, 'stage': stage,'processing_complete':True,
            'generated_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
            'script': rel(Path(__file__)),
            'coverage': {'ledger_addresses': metric(len(index), 'addresses'),
                         'ledger_addresses_with_readable_timelines': metric(len(found), 'addresses'),
                         'ledger_addresses_without_readable_timelines': metric(len(index)-len(found), 'addresses'),
                         'unreadable_or_partial_files': metric(sum(m['status'] != 'readable' for m in manifest), 'files'),
                         'nonledger_timelines': metric(extras, 'chain-address timelines')},
            'timeline_manifest': manifest}
    if stage!='loader':
        listed=[summaries.get(key) or blank_summary(meta) for key,meta in sorted(index.items())]
        for r in listed+same_address: r['sdn_names']=[names.get(uid,uid) for uid in r['sdn_uids']]
        result.update(addresses=listed, same_address_other_evm_chain=same_address)
        result['coverage'].update(complete_ledger_histories=metric(sum(r['history_complete'] for r in listed),'addresses'),
            ledger_addresses_with_T_balance=metric(sum(r['balance_at_designation_usd'] is not None for r in listed),'addresses'),
            ledger_addresses_with_today_balance=metric(sum(r['still_there_today_usd'] is not None for r in listed),'addresses'))
    result['input_hashes']={rel(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
        [ROOT/'data/addresses.csv',ROOT/'data/ledger.csv',ROOT/'data/actions.csv',ROOT/'data/labels/labels.csv',
         ROOT/'scripts/prices/price.py',*sorted((ROOT/'data/prices').glob('*.csv*'))]}
    return result


def csv_text(result):
    output=io.StringIO(newline='')
    fields=['chain','address','view','listed_date','sdn_uids','sdn_names','programs','trackable',
            'untrackable_reason','history_complete','exchange_scale','tornado_contract','tornado_excluded',
            'balance_at_designation_usd','still_there_today_usd','moved_after','moved_before','received_after',
            'first_outflow_lag_days','first_outflow_exact_within_checked_history','last_outflow_before_lag_days',
            'total_inflow_after_usd','priced_inflow_after_subtotal_usd','checked_through_utc',
            'share_T_balance_gone','checkpoints','examples','quality','reconciliation','source_url','raw_ref']
    writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore'); writer.writeheader()
    for r in result.get('addresses',[])+result.get('same_address_other_evm_chain',[]):
        packed=dict(r)
        packed['tornado_excluded']=bool(tornado_excluded(r))
        if r.get('checkpoints'):
            packed['checkpoints'],packed['reconciliation'],packed['examples']=pack_detail(r)
        writer.writerow({k:json.dumps(packed.get(k),separators=(',',':'),allow_nan=False) if isinstance(packed.get(k),(dict,list))
                         else packed.get(k) for k in fields})
    text=output.getvalue()
    if len(text.encode())>20*1024*1024: raise RuntimeError('Owned CSV exceeds the 20 MB contract; reduce inline detail before saving')
    return text


def pack_detail(r):
    """Lossless columnar JSON, sharing long evidence strings within a CSV row."""
    refs=[]; ref_ids={}; price_rows=[]; price_ids={}
    def ref(value):
        if value is None: return None
        key=json.dumps(value,separators=(',',':'))
        if key not in ref_ids: ref_ids[key]=len(refs); refs.append(value)
        return ref_ids[key]
    def price(q):
        if q is None: return None
        value=[q['price_usd'],ref(q['valued_at']),ref(q['source']),ref(q['raw_ref']),ref(q['source_url'])]
        key=json.dumps(value)
        if key not in price_ids: price_ids[key]=len(price_rows); price_rows.append(value)
        return price_ids[key]
    def series(values): return values[0] if all(v==values[0] for v in values) else values
    labels=list(r['checkpoints']); cps=[r['checkpoints'][k] for k in labels]
    cp={'format':'columnar-v1','labels':labels,'times':[c['time_utc'] for c in cps],
        'usd':[c['recognised_assets_usd']['value'] for c in cps],
        'priced_subtotal_usd':[c['priced_subtotal_usd']['value'] for c in cps],
        'missing':[c['unavailable_recognised_assets'] for c in cps],
        'unrecognised_positive':[c['unrecognised_positive_balances'] for c in cps], 'assets':{},'refs':refs,'prices':price_rows}
    methods={'unavailable':0,'reconciled_transfer_history':1,'observed':2}
    maps=[{a['asset']:a for a in c['assets']} for c in cps]
    for asset in maps[0]:
        aa=[m[asset] for m in maps]
        cp['assets'][asset]=[aa[0]['symbol'],series([a['native'] for a in aa]),series([a['usd'] for a in aa]),
            series([ref(a['valued_at']) for a in aa]),series([price(a['price']) for a in aa]),
            series([methods[a['method']] for a in aa]),series([ref(a['raw_ref']) for a in aa])]
    recon={'format':'columnar-v1','assets':{a['asset']:[a['symbol'],a['reconstructed_native'],a['observed_native'],a['minimum_native'],
         a['pass'],a['historical_usable'],a['same_history_block'],ref(a['raw_ref'])] for a in r['reconciliation']}}
    events=[]; event_ids={}
    def event(e):
        if e is None: return None
        key=json.dumps(e,sort_keys=True)
        if key not in event_ids:
            ev=dict(e,price=price(e['price']),raw_ref=ref(e['raw_ref']))
            event_ids[key]=len(events); events.append(ev)
        return event_ids[key]
    examples={'format':'columnar-v1','events':events}
    for k,v in r['examples'].items(): examples[k]=[event(e) for e in v] if isinstance(v,list) else event(v)
    return cp,recon,examples


def unpack_detail(cp,recon,examples):
    if cp.get('format')!='columnar-v1': return cp,recon,examples
    refs=cp['refs']; labels=cp['labels']; methods=['unavailable','reconciled_transfer_history','observed']
    def ref(i): return refs[i] if i is not None else None
    def price(i):
        if i is None: return None
        p=cp['prices'][i]
        return dict(price_usd=p[0],valued_at=ref(p[1]),source=ref(p[2]),raw_ref=ref(p[3]),source_url=ref(p[4]))
    def at(v,i): return v[i] if isinstance(v,list) else v
    full={}
    for i,name in enumerate(labels):
        assets=[]
        for asset,a in cp['assets'].items():
            assets.append(dict(asset=asset,symbol=a[0],native=at(a[1],i),usd=at(a[2],i),valued_at=ref(at(a[3],i)),
                price=price(at(a[4],i)),method=methods[at(a[5],i)],raw_ref=ref(at(a[6],i))))
        t=cp['times'][i]
        full[name]=dict(time_utc=t,assets=assets,recognised_assets_usd=metric(cp['usd'][i],'usd',t or 'unavailable'),
            priced_subtotal_usd=metric(cp['priced_subtotal_usd'][i],'usd',t or 'unavailable'),
            unavailable_recognised_assets=cp['missing'][i],unrecognised_positive_balances=cp['unrecognised_positive'][i])
    rr=[dict(asset=asset,symbol=a[0],reconstructed_native=a[1],observed_native=a[2],minimum_native=a[3],
        **{'pass':a[4]},historical_usable=a[5],same_history_block=a[6],raw_ref=ref(a[7])) for asset,a in recon['assets'].items()]
    events=[dict(e,price=price(e['price']),raw_ref=ref(e['raw_ref'])) for e in examples['events']]
    ee={k:([events[i] for i in v] if isinstance(v,list) else events[v] if v is not None else None)
        for k,v in examples.items() if k not in {'format','events'}}
    return full,rr,ee


def load_saved():
    """Aggregate the early balance-stage checkpoint without another long scan."""
    result=json.loads(OUT.read_text())
    if not result.get('processing_complete'): raise RuntimeError('Balance pass is still incomplete; finish a normal run first')
    if result.get('address_summary_sha256') and hashlib.sha256(CSV.read_bytes()).hexdigest()!=result['address_summary_sha256']:
        raise RuntimeError('Saved CSV checksum differs from the result snapshot')
    result['addresses']=[]; result['same_address_other_evm_chain']=[]
    csv.field_size_limit(100*1024*1024)
    for r in rows(CSV):
        for key in ['sdn_uids','sdn_names','programs','share_T_balance_gone','checkpoints','examples','quality','reconciliation']:
            r[key]=json.loads(r[key])
        r['checkpoints'],r['reconciliation'],r['examples']=unpack_detail(r['checkpoints'],r['reconciliation'],r['examples'])
        for key in ['trackable','history_complete','exchange_scale','tornado_contract','moved_after','moved_before',
                    'received_after','first_outflow_exact_within_checked_history']:
            r[key]={'True':True,'False':False,'':None}.get(r[key])
        for key in ['balance_at_designation_usd','still_there_today_usd','first_outflow_lag_days','last_outflow_before_lag_days',
                    'total_inflow_after_usd','priced_inflow_after_subtotal_usd']:
            r[key]=float(r[key]) if r[key] else None
        r['timeline']=r['raw_ref'] if r['raw_ref'].startswith('data/timelines/') else None
        result['addresses' if r['view']=='listed_chain' else 'same_address_other_evm_chain'].append(r)
    result['stage']='aggregates'
    assert len(result['addresses'])==result['coverage']['ledger_addresses']['value']
    return result


def summarize(group):
    entities=set(uid for r in group for uid in r['sdn_uids'])
    with_T=[r for r in group if r['balance_at_designation_usd'] is not None]
    with_today=[r for r in group if r['still_there_today_usd'] is not None]
    moved=[r for r in group if r['moved_after'] is True]
    received=[r for r in group if r['received_after'] is True]
    def uids(rs): return {u for r in rs for u in r['sdn_uids']}
    entity_rows=collections.defaultdict(list)
    for r in group:
        for uid in r['sdn_uids']: entity_rows[uid].append(r)
    no_move_entities=sum(all(r['moved_after'] is False for r in rs) for rs in entity_rows.values())
    unknown_move_entities=sum(not any(r['moved_after'] is True for r in rs) and not all(r['moved_after'] is False for r in rs)
        for rs in entity_rows.values())
    result={
        'raw_ref':'data/derived/address_summary.csv#filters-in-enclosing-group-population-and-scope',
        'addresses':metric(len(group),'addresses'), 'entities':metric(len(entities),'entities'),
        'timelines':metric(sum(bool(r['timeline']) for r in group),'addresses'),
        'complete_history':metric(sum(r['history_complete'] for r in group),'addresses'),
        'exchange_scale':metric(sum(r['exchange_scale'] is True for r in group),'addresses'),
        'addresses_with_T_balance':metric(len(with_T),'addresses'),
        'entities_with_any_T_balance':metric(len(uids(with_T)),'entities'),
        'value_at_designation_priced_usd':metric(sum(r['balance_at_designation_usd'] for r in with_T) if with_T else None,
             'usd','each address balance at its own T, valued at that T; mixed historical dates'),
        'addresses_with_today_balance':metric(len(with_today),'addresses'),
        'entities_with_any_today_balance':metric(len(uids(with_today)),'entities'),
        'value_today_priced_usd':metric(sum(r['still_there_today_usd'] for r in with_today) if with_today else None,
             'usd','each address latest fetched balance, valued at that observation time; CSV gives exact times'),
        'moved_after_addresses':metric(len(moved),'addresses'),
        'moved_after_entities':metric(len(uids(moved)),'entities'),
        'no_outflow_found_addresses':metric(sum(r['moved_after'] is False for r in group),'addresses'),
        'no_outflow_found_entities':metric(no_move_entities,'entities'),
        'movement_unknown_addresses':metric(sum(r['moved_after'] is None for r in group),'addresses'),
        'movement_unknown_entities':metric(unknown_move_entities,'entities'),
        'moved_before_addresses':metric(sum(r['moved_before'] is True for r in group),'addresses'),
        'moved_before_entities':metric(len(uids([r for r in group if r['moved_before'] is True])),'entities'),
        'received_after_addresses':metric(len(received),'addresses'),
        'received_after_entities':metric(len(uids(received)),'entities'),
        'receipts_unknown_addresses':metric(sum(r['received_after'] is None for r in group),'addresses'),
        'empty_T_recognised_assets_addresses':metric(sum(r['balance_at_designation_usd']==0 for r in with_T),'addresses'),
        'dust_only_T_recognised_assets_addresses':metric(sum(0<r['balance_at_designation_usd']<1 for r in with_T),'addresses'),
        'priced_inflow_after_subtotal_usd':metric(sum(r['priced_inflow_after_subtotal_usd'] or 0 for r in group),
             'usd','at each transfer time; recognised assets and transfers >=1 USD only'),
        'inflow_total_known_addresses':metric(sum(r['total_inflow_after_usd'] is not None for r in group),'addresses'),
    }
    known=[r for r in group if r['moved_after'] is not None]
    result['share_moved_after_among_known']=metric(len(moved)/len(known) if known else None,'share')
    lags=[r['first_outflow_lag_days'] for r in group if r.get('first_outflow_exact_within_checked_history') and r['first_outflow_lag_days'] is not None]
    result['first_outflow_median_days_among_observed_movers']=metric(statistics.median(lags) if lags else None,'days')
    result['first_outflow_median_denominator']=metric(len(lags),'addresses')
    # This conditional median is deliberately not a median over all sanctioned
    # addresses: non-movers are right censored and incomplete histories excluded.
    result['depletion']={}
    for cp in ['T+7d','T+30d','T+365d','today']:
        cohort=[r for r in group if r['share_T_balance_gone'][cp] is not None]
        den=sum(r['balance_at_designation_usd'] for r in cohort)
        gone=sum(r['balance_at_designation_usd']*r['share_T_balance_gone'][cp] for r in cohort)
        result['depletion'][cp]={
            'share':metric(gone/den if den else None,'share'),
            'T_value_denominator':metric(den if cohort else None,'usd','each address own T price'),
            'net_depleted_T_value':metric(gone if cohort else None,'usd','each address own T price'),
            'addresses':metric(len(cohort),'addresses'), 'entities':metric(len(uids(cohort)),'entities')}
    return result


def aggregates(result):
    listed=result['addresses']; tables={}
    dimensions={
        'overall':lambda r:['all'], 'by_chain':lambda r:[r['chain']],
        'by_program':lambda r:r['programs'] or ['unknown'],
        'by_designation_year':lambda r:[r['listed_date'][:4]],
        'tron_vs_everything_else':lambda r:['Tron' if r['chain']=='TRX' else 'everything_else'],
    }
    for dimension,keyfunc in dimensions.items():
        table=[]
        for population in ['all_listed','excluding_tornado_contracts']:
            population_rows=[r for r in listed if population=='all_listed' or not tornado_excluded(r)]
            for scale in ['including_exchange_scale','excluding_exchange_scale']:
                population_rows_scale=[r for r in population_rows if scale=='including_exchange_scale' or r['exchange_scale'] is not True]
                grouped=collections.defaultdict(list)
                for r in population_rows_scale:
                    for key in keyfunc(r): grouped[(key,'trackable' if r['trackable'] else 'untrackable')].append(r)
                for (key,status),rs in sorted(grouped.items()):
                    table.append(dict(group=key,trackability=status,population=population,exchange_scale_scope=scale,**summarize(rs)))
        tables[dimension]=table
    result['aggregates']=tables
    result['same_address_other_evm_aggregates']={chain:summarize([r for r in result['same_address_other_evm_chain'] if r['chain']==chain])
          for chain in sorted({r['chain'] for r in result['same_address_other_evm_chain']})}
    ordinary=[r for r in listed if not tornado_excluded(r) and r['trackable']]
    small=[r for r in ordinary if r['exchange_scale'] is not True]
    result['headline_population']=summarize(ordinary)
    result['headline_population_without_exchange_scale']=summarize(small)
    # Keep example transactions attached to each candidate; CSV contains the
    # full per-address computation and source trail.
    depleted=sorted([r for r in ordinary if r['share_T_balance_gone']['T+7d'] is not None],
                    key=lambda r:r['balance_at_designation_usd']*r['share_T_balance_gone']['T+7d'],reverse=True)
    retained=sorted([r for r in ordinary if r['still_there_today_usd'] is not None],key=lambda r:r['still_there_today_usd'],reverse=True)
    empty=[r for r in ordinary if r['balance_at_designation_usd']==0 and r['examples'].get('last_outflow_before')]
    empty.sort(key=lambda r:r['examples']['last_outflow_before']['usd']['value'],reverse=True)
    def examples(rs,kind,limit=3):
        found=[]; hashes=set()
        for r in rs:
            candidates=r['examples'].get(kind) or []
            if isinstance(candidates,dict): candidates=[candidates]
            for ev in candidates:
                if ev['hash'] not in hashes:
                    found.append(dict(ev,sanctioned_address=r['address'],sdn_names=r['sdn_names'],listed_date=r['listed_date']))
                    hashes.add(ev['hash'])
                if len(found)==limit: return found
        return found
    def brief(r):
        return {k:r[k] for k in ['chain','address','sdn_uids','sdn_names','listed_date','balance_at_designation_usd',
            'still_there_today_usd','history_complete','exchange_scale','raw_ref']}
    result['rankings']={'largest_balances_today':[brief(r) for r in retained[:20]],
                        'empty_at_T_with_prior_outflow':[brief(r) for r in empty[:20]],
                        'largest_7d_depletions':[dict(brief(r),share_gone_7d=r['share_T_balance_gone']['T+7d']) for r in depleted[:20]]}
    blacklist_context=[]
    freeze_path=ROOT/'data/freezes.csv'
    if freeze_path.exists():
        result['input_hashes'][rel(freeze_path)]=hashlib.sha256(freeze_path.read_bytes()).hexdigest()
        active={}
        for e in sorted(rows(freeze_path),key=lambda e:(e['timestamp'],int(e.get('block') or 0),int(e.get('log_index') or 0))):
            chain=e['chain'].upper(); address=norm(chain,e['address_normalized']); asset=e['contract']
            if chain in EVM: asset=asset.lower()
            key=(chain,address,asset)
            if e['event'] in {'AddedBlackList','Blacklisted'}: active[key]=e
            elif e['event'] in {'RemovedBlackList','UnBlacklisted'}: active.pop(key,None)
        for r in retained[:20]:
            for a in r['checkpoints']['today']['assets']:
                e=active.get((r['chain'],r['address'],a['asset']))
                if a['symbol']=='USDT' and a['usd'] and e:
                    blacklist_context.append({'kind':'blacklist_context','chain':r['chain'],'hash':e['tx_hash'],
                       'explorer_url':explorer(r['chain'],e['tx_hash']),'time_utc':e['timestamp'],
                       'sanctioned_address':r['address'],'sdn_names':r['sdn_names'],'listed_date':r['listed_date'],
                       'latest_balance_usd':metric(a['usd'],'usd',a['valued_at']),
                       'latest_balance_native':metric(a['native'],'native:'+a['asset']),
                       'raw_ref':e['raw_ref'],'balance_raw_ref':a['raw_ref'],'price':a['price']})
    result['retained_blacklist_context']=blacklist_context
    seven=result['headline_population']['depletion']['T+7d']
    result['findings']=[
      {'id':'seven_day_depletion', 'number':seven['share'], 'denominator':seven,
       'statement':'Share of observed, reconciled designation-date value net-depleted within seven days, excluding Tornado-associated identifiers.',
       'examples':examples([r for r in depleted if r['examples'].get('first_outflow') and r['first_outflow_lag_days']<7],'first_outflow'),
       'confidence':'Provisional observed subset, not all sanctioned crypto value. Mixed own-T prices. Replenishment can hide withdrawals; price changes cannot create depletion. Unknown/unreconciled balances excluded.'},
      {'id':'largest_balances_today', 'number':metric(sum(r['still_there_today_usd'] for r in retained[:10]),'usd',
             'each of the ten address latest fetched balance times; exact valuations in CSV'),
       'statement':'Recognised-asset value currently observed at the ten largest listed non-Tornado chain-address pairs.',
       'examples':examples(retained,'funding_any_time') or examples(retained,'largest_inflows'),
       'confidence':'Direct saved latest-state observations; not proof funds are unfrozen, spendable or the original designation-date units. Same assets elsewhere excluded. Example transactions illustrate receipts, not the state balance itself.'},
      {'id':'empty_when_listed','number':metric(len(empty),'addresses'),
       'statement':'Listed non-Tornado chain-address pairs with zero reconciled recognised-asset balance at T and an earlier non-dust outflow.',
       'examples':examples(empty,'last_outflow_before'),
       'confidence':'Zero concerns recognised assets only; does not exclude unpriced tokens, off-address holdings or later deposits. Earlier movement does not imply knowledge of sanctions.'},
    ]
    if blacklist_context:
        result['findings'].append({'id':'retained_blacklisted_usdt',
          'number':metric(sum(e['latest_balance_usd']['value'] for e in blacklist_context),'usd',
              'at each latest saved USDT balance observation; exact times in examples and CSV'),
          'statement':f"USDT observed at {len(blacklist_context)} of the twenty largest non-Tornado listed chain-address pairs whose issuer blacklist was active at the end of saved event history.",
          'addresses':metric(len(blacklist_context),'addresses'), 'examples':blacklist_context[:3],
          'confidence':'Latest balances are not freeze-time amounts. Blacklist state is replayed from saved add/remove logs, not a new live contract call. This is context for retained value, not proof of original holdings, spendability of other assets, or a legal conclusion.'})
    footprints=collections.defaultdict(list)
    for r in depleted:
        for uid in r['sdn_uids']: footprints[uid].append(r)
    ranked=sorted(footprints,key=lambda uid:sum(r['balance_at_designation_usd'] for r in footprints[uid]),reverse=True)
    result['concentration_sensitivity']=[]
    total=seven['T_value_denominator']['value'] or 0
    for uid in ranked[:3]:
        rs=footprints[uid]; value=sum(r['balance_at_designation_usd'] for r in rs)
        result['concentration_sensitivity'].append({'entity_uid':uid,
           'raw_ref':f'data/derived/address_summary.csv#listed_chain;sdn_uids_contains={uid};T+7d_share_known',
           'sdn_names':sorted({name for r in rs for u,name in zip(r['sdn_uids'],r['sdn_names']) if u==uid}),
           'addresses_in_7d_cohort':metric(len(rs),'addresses'),
           'cohort_value_at_T':metric(value,'usd','each address own T price'),
           'share_of_7d_value_denominator':metric(value/total if total else None,'share'),
           'excluding_this_entity':summarize([r for r in ordinary if uid not in r['sdn_uids']])})
    if result['concentration_sensitivity']:
        top=result['concentration_sensitivity'][0]
        result['findings'].insert(0,{'id':'value_denominator_concentration','number':top['share_of_7d_value_denominator'],
          'statement':f"Share of the observed seven-day T-value denominator attached to SDN UID {top['entity_uid']} ({'; '.join(top['sdn_names'])}).",
          'examples':examples(footprints[top['entity_uid']],'funding_any_time'),
          'confidence':'Describes address-list concentration, not beneficial ownership, spendability or custody. Public seizures and freezes can leave funds at listed addresses. Entity footprints overlap; do not add them. See exclusion sensitivity.'})
    program_candidates=[]
    for table_row in result['aggregates']['by_program']:
        if (table_row['population']=='excluding_tornado_contracts' and table_row['trackability']=='trackable'
            and table_row['exchange_scale_scope']=='including_exchange_scale' and table_row['first_outflow_median_denominator']['value']>=5):
            program_candidates.append(table_row)
    if program_candidates:
        p=min(program_candidates,key=lambda r:r['first_outflow_median_days_among_observed_movers']['value'])
        rs=[r for r in ordinary if p['group'] in r['programs'] and r.get('first_outflow_exact_within_checked_history') and r['first_outflow_lag_days'] is not None]
        rs.sort(key=lambda r:abs(r['first_outflow_lag_days']-p['first_outflow_median_days_among_observed_movers']['value']))
        result['findings'].append({'id':'first_move_by_program', 'number':p['first_outflow_median_days_among_observed_movers'],
           'denominator_addresses':p['first_outflow_median_denominator'],
           'statement':f"Conditional median first-outflow lag among observed {p['group']} movers, the lowest program median with at least five eligible movers in this snapshot.",
           'examples':examples(rs,'first_outflow'),
           'confidence':'Exploratory ranking, not a causal or population-wide speed estimate. Complete histories and priced non-dust movers only; non-movers excluded, programs overlap, and publication time is a noon ET estimate with up to 12 hours uncertainty.'})
    result['method']={
        'T':'00:00 America/New_York on the first publication date; T balance excludes transactions at or after T',
        'T_pub':'12:00 America/New_York; first outflow is first >=T, lag against T_pub may be negative on the designation morning',
        'checkpoints':'T-7d, T, T+7d, T+30d, T+365d use ET calendar dates; future or uncovered endpoints are null; today is each latest saved state',
        'depletion':'sum_asset(max(0, balance_T - balance_checkpoint) * price_T) / sum_asset(balance_T * price_T); no lot tracing; recognised priced assets only',
        'balances':"from-zero signed transfer amounts minus fees, only on complete histories that reconcile per asset with current saved state; today's direct observations remain usable on incomplete histories",
        'prices':'scripts/prices/price.py usd(); checkpoint time or transfer time. WETH/ETH, WBTC/BTC, and BSC pegged USDT/USDC use underlying-price proxies, not independent wrapper market quotes',
        'dust_and_spam':'recognised-contract/native transfers >=1 USD at transfer time; unknown contracts and zero amounts excluded. Unknown asset native quantities remain in CSV, never valued from ticker',
        'inflows':'total_inflow_after_usd covers non-dust recognised assets only; partial/unpriced recognised histories return null plus a priced subtotal',
        'first_outflow_median':'conditional on observed non-dust movers with complete history and prices, not population survival time; non-movers are censored',
        'entities':'distinct SDN UIDs in each row/group, not persons or independent wallets; groups/programs overlap and must not be added',
        'same_address_other_chain':'separate view, anchored at the earliest publication of the same 0x string on a listed EVM chain; excluded from listed-chain aggregates',
        'untrackable':'ledger trackable flag preserved, shown in separate rows even where a fetcher later found a working route (e.g. BTG)',
        'exchange_scale':'more than 10,000 distinct observed transaction hashes, or fetcher huge_address/reported_history_records >10,000; incomplete lower-count histories may conceal scale',
        'tornado_exclusion':'primary population excludes all identifiers under an OFAC name containing TORNADO, plus independently identified pool/router/proxy addresses; matches the pre-move reference. tornado_contract retains the narrower role flag; tornado_excluded records the broader population rule',
        'provisional':'fetchers still active; the manifest hashes identify this read pass, not a simultaneous multi-chain snapshot',
    }
    result['recognised_asset_registry']={'native':NATIVE,'tokens':TOKENS}
    return result


def compact_result(result):
    """The full audit table is the CSV; keep the web-facing summary small."""
    for rs in result.get('rankings',{}).values():
        for r in rs:
            r['balance_at_designation_usd']=metric(r['balance_at_designation_usd'],'usd',
                iso(dt.datetime.fromisoformat(r['listed_date']).replace(tzinfo=ET).timestamp()))
            r['still_there_today_usd']=metric(r['still_there_today_usd'],'usd','each latest saved asset observation; exact times in CSV')
            if 'share_gone_7d' in r: r['share_gone_7d']=metric(r['share_gone_7d'],'share')
    for key in ['addresses','same_address_other_evm_chain']:
        if key not in result: continue
        compact=[]
        for r in result[key]:
            c={k:r[k] for k in ['chain','address','view','listed_date','sdn_uids','sdn_names','programs','trackable',
                'untrackable_reason','history_complete','exchange_scale','tornado_contract','moved_before','moved_after',
                'received_after','raw_ref','source_url']}
            c['tornado_excluded']=bool(tornado_excluded(r))
            for k in ['balance_at_designation_usd','still_there_today_usd','total_inflow_after_usd','priced_inflow_after_subtotal_usd']:
                when = r.get('checkpoints',{}).get('T' if k=='balance_at_designation_usd' else 'today',{}).get('time_utc')
                if 'inflow' in k: when='at each transfer time; recognised assets >=1 USD'
                c[k]=metric(r[k],'usd',when or 'not observed')
            c['first_outflow_lag_days']=metric(r['first_outflow_lag_days'],'days')
            c['share_T_balance_gone']={k:metric(v,'share') for k,v in r['share_T_balance_gone'].items()}
            compact.append(c)
        result[key]=compact
    return result


def report(result):
    coverage=result['coverage']
    lines=['# Checkpoints — provisional', '',
           f"Saved-data read pass completed {result['generated_at_utc']}. **{('Provisional: chain fetchers remain active.' if result.get('provisional', True) else 'Provisional: false. Bounded acquisition finished; per-chain, asset and reconciliation gaps remain.')}**", '',
           'Research, not legal or compliance advice. No outflow found means within the data checked. Identifiers and SDN UIDs are not persons or proof of control.', '',
           '## Coverage and outputs', '',
           '| Measure | Count | Unit |','|---|---:|---|']
    for key,v in coverage.items(): lines.append(f"| {key} | {v['value']} | {v['unit']} |")
    lines+=['',
       '`data/derived/address_summary.csv` has one row per listed chain-address plus explicitly separated same-address other-EVM-chain rows. '
       'Its `checkpoints` JSON cell holds per-asset native quantities, historical USD, requested/actual valuation times, price observations and raw references; '
       '`reconciliation` exposes pass/fail per asset. Booleans are True/False; an empty scalar cell or JSON null means unknown, never zero. '
       'USD scalar column units are in their names. `share_T_balance_gone` is a fraction (0–1), and lag columns are days. '
       '`examples` contains transaction hashes, explorer URLs, timeline row indexes and saved API/price evidence.', '',
       '`results/checkpoints.json` contains compact address indexes, all aggregates, rankings, candidate findings, source hashes and the timeline manifest. '
       'Source request metadata is in the gzip referenced by each timeline row (or the adjacent price `.request.json`). '
       'T comes from `data/addresses.csv`; match the chain/address in `data/ledger.csv` for `listed_raw_ref`, `listed_action_url` and `listing_events` providing its OFAC publication evidence. '
       'Aggregate rows point to the address CSV and explicitly name their filters; program and entity memberships overlap.', '',
       '### CSV detail encoding', '',
       'Long evidence strings are losslessly deduplicated inside each row. `unpack_detail(checkpoints, reconciliation, examples)` in the script restores conventional per-checkpoint objects. '
       'For `columnar-v1`, checkpoint `labels` fixes the order; `times`, `usd`, `priced_subtotal_usd`, `missing`, and `unrecognised_positive` follow that order. '
       'Each `assets[asset]` is `[symbol, native, usd, valued_at_ref, price_id, method, raw_ref_id]`. A scalar series repeats at every checkpoint; a list has one item per label. '
       'Methods: 0 unavailable, 1 reconciled transfer history, 2 observed state. Reference IDs index `refs` (which may hold a string or a raw-reference list). '
       'Each `prices[id]` is `[price_usd, observed_time_ref, source_ref, raw_ref_id, source_url_ref]`. '
       'Each reconciliation `assets[asset]` is `[symbol, reconstructed_native, observed_native, minimum_native, pass, historical_usable, same_history_block, raw_ref_id]`. '
       'Examples share those refs/prices and store unique events once; named example fields are event indexes or lists of indexes. '
       'Native quantities are decimal strings in the asset’s own units; USD series are checkpoint-time USD, prices are USD per unit, and missing/unknown series count assets. '
       'The compact format avoids a large repeated-evidence file while preserving quantities and their provenance.', '',
       '## Reproduce', '',
       '```sh', '.venv/bin/python -S scripts/analysis/checkpoints.py',
       '.venv/bin/python -S scripts/analysis/checkpoints.py --self-test',
       '.venv/bin/python -S scripts/analysis/checkpoints.py --check', '```', '',
       '`--check` recomputes the saved timeline-file manifest offline and compares the saved result and CSV. Newly arrived files are outside that published snapshot; changed existing files correctly produce a diff. Rerun the default command to refresh. '
       'Inputs are not locked: each timeline is read once, hashed, and unreadable/partial files are skipped and counted. '
       'JSON/gzip parse errors do not stop other addresses. A parseable incomplete history stays flagged. '
       'This check runs offline without credentials.', '']
    if 'method' not in result: return '\n'.join(lines)
    lines+=['## Candidate findings', '']
    for f in result['findings']:
        n=f['number']; display=f"{n['value']:.4%}" if n['unit']=='share' and n['value'] is not None else str(n['value'])
        lines += [f"### {f['id']}", '', f"**{display} {n['unit']}** — {f['statement']}", '']
        if n.get('valued_at'): lines += ['Valuation: '+n['valued_at']+'.','']
        if f.get('denominator_addresses'): lines += [f"Denominator: {f['denominator_addresses']['value']} addresses with observed non-dust first outflows.", '']
        if 'denominator' in f:
            d=f['denominator']; lines += [f"Denominator: {d['addresses']['value']} addresses; {d['entities']['value']} SDN UID entities; "
                f"{d['T_value_denominator']['value']} USD at each address’s own T. Depleted value: {d['net_depleted_T_value']['value']} USD at the same T prices.", '']
        lines += ['Confidence: '+f['confidence'],'']
        for ev in f['examples']:
            if ev.get('kind')=='blacklist_context':
                lines += [f"- {ev['chain']} [{ev['hash']}]({ev['explorer_url']}) — issuer blacklist event {ev['time_utc']} for "
                    f"`{ev['sanctioned_address']}` ({'; '.join(ev['sdn_names'])}). Latest USDT balance: {ev['latest_balance_native']['value']} token units; "
                    f"{ev['latest_balance_usd']['value']:.2f} USD valued at {ev['latest_balance_usd']['valued_at']}. "
                    f"Event raw: `{ev['raw_ref']}`; balance raw: `{ev['balance_raw_ref']}`; price raw: `{ev['price']['raw_ref']}`."]
                continue
            lines += [f"- {ev['chain']} [{ev['hash']}]({ev['explorer_url']}) — {ev['time_utc']}; "
                f"{ev['amount']['value']} {ev['amount']['unit']}; {ev['usd']['value']:.2f} USD at transfer time. "
                f"Address `{ev.get('sanctioned_address','')}` ({'; '.join(ev.get('sdn_names',[]))}), first listed {ev.get('listed_date','unknown')}. "
                f"Raw: `{ev['raw_ref']}`; price raw: `{ev['price']['raw_ref']}`."]
        lines+=['']
    lines+=['## Largest balances observed today', '',
            'Listed non-Tornado chain-address pairs. USD at each asset’s saved latest observation time; see CSV for exact time and price. '
            'These are balances at the address, including frozen funds if present, not proof of spendability or retention of the original units.', '',
            '| Chain | Address | OFAC name(s) | USD at latest observation |','|---|---|---|---:|']
    for r in result['rankings']['largest_balances_today'][:10]:
        lines.append(f"| {r['chain']} | `{r['address']}` | {'; '.join(r['sdn_names'])} | {r['still_there_today_usd']:,.2f} |")
    lines+=['','## Chain and program comparisons', '',
            'These tables conservatively exclude every identifier listed under an OFAC name containing TORNADO, plus independently identified pool/router/proxy addresses, matching the pre-move reference. '
            '`tornado_contract` preserves the narrower role flag and `tornado_excluded` records this broader population rule. '
            'Exchange-scale addresses remain included here; JSON contains both scale scopes and the all-listed population. '
            'Program membership and SDN UIDs overlap; do not sum program rows. Untrackable is the ledger flag, retained even if a fetcher later found a route.', '']
    lines+=['### Concentration sensitivity', '',
            '| SDN UID | OFAC name | Share of observed 7d T-value denominator | 7d depletion share excluding that UID |',
            '|---|---|---:|---:|']
    for c in result.get('concentration_sensitivity',[]):
        share=c['share_of_7d_value_denominator']['value']; gone=c['excluding_this_entity']['depletion']['T+7d']['share']['value']
        lines.append(f"| {c['entity_uid']} | {'; '.join(c['sdn_names'])} | {share:.2%} | {gone:.2%} |" if gone is not None else
                     f"| {c['entity_uid']} | {'; '.join(c['sdn_names'])} | {share:.2%} | unknown |")
    lines+=['']
    for dimension in ['by_chain','by_program','tron_vs_everything_else']:
        lines += ['### '+dimension, '',
                  '| Group | Ledger status | Addresses | Entities | T balance known (addresses) | Moved after (addresses) | Received after (addresses) | 7d depletion share | First move median (days; movers n) |',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|']
        for r in result['aggregates'][dimension]:
            if r['population']!='excluding_tornado_contracts' or r['exchange_scale_scope']!='including_exchange_scale': continue
            s=r['depletion']['T+7d']['share']['value']; lag=r['first_outflow_median_days_among_observed_movers']['value']
            ss=f'{s:.2%}' if s is not None else 'unknown'; ls=f"{lag:.3f}; {r['first_outflow_median_denominator']['value']}" if lag is not None else 'unknown; 0'
            lines.append(f"| {r['group']} | {r['trackability']} | {r['addresses']['value']} | {r['entities']['value']} | "
               f"{r['addresses_with_T_balance']['value']} | {r['moved_after_addresses']['value']} | {r['received_after_addresses']['value']} | {ss} | {ls} |")
        lines+=['']
    lines+=['## Method and limits', '']
    for k,v in result['method'].items(): lines += [f'- **{k}:** {v}']
    lines += ['',
       'All value totals are recognised-asset subtotals, not an estimate of unpriced holdings. Unknown/spam token quantities remain unvalued. '
       'From-zero reconstruction and a matching latest state are necessary checks, not proof of indexer completeness or absence of offsetting omissions. '
       'A stablecoin issuer burn can change state without a Transfer event; mismatches are not attributed to withdrawals. '
       'Per-asset reconciliation failure suppresses its historical checkpoints. A full-address recognised-asset total is null if a recognised asset is missing, even when other assets are known.', '',
       'Ethereum Tornado pools have separately scoped event/daily archive data: whole-address coverage.complete is false, so this script leaves historical checkpoints unknown rather than presenting daily samples as midnight balances. '
       'BSC/Base and unavailable-chain stubs have explicit history gaps. Tron staking/reward/resource changes may prevent native reconciliation; native-coin failure does not invalidate a separately reconciled USDT asset, but does suppress the full recognised-asset address total. '
       'Solana token-account discovery remains incomplete. BNB Beacon snapshots are legacy state, not evidence of current spendability or BSC recovery holdings. '
       'See `docs/COVERAGE.md` and `docs/sources/{EVM,TRON,UTXO,PRICES}.md` for source-specific limits.', '',
       'Post-T observations run through the latest fetched head, including periods after any delisting. They are “after first publication,” not a statement that an address remained sanctioned throughout. '
       'Future T+365d checkpoints remain unknown. Comparisons across checkpoints can use different eligible cohorts; each JSON depletion cell reports its own address/entity/USD denominator.', '',
       'New relative to the prior Ethereum and Bitcoin papers: one consistent chain-address table across listed chains, a separately labelled other-EVM-chain view, recognised-token/native per-asset reconciliation, and program/year/Tron and scale sensitivities. '
       'This provisional snapshot is not yet a complete cross-chain population estimate.', '']
    return '\n'.join(lines)


def self_test():
    global quote
    original=quote
    quote=lambda symbol,t: {'price_usd':2.,'valued_at':iso(t),'source':'synthetic','raw_ref':'synthetic','source_url':'synthetic'} if symbol else None
    try:
        meta={'chain':'BTC','address_normalized':'synthetic','first_listed_date':'2020-03-02','sdn_uids':'one',
              'programs':'TEST','trackable':'true','raw_ref':'synthetic','source_url':'synthetic'}
        T=dt.datetime(2020,3,2,tzinfo=ET).timestamp()
        def tx(day,direction,amount,fee='0',**extra):
            return dict(hash=str(day)+direction+amount,block=1,time_utc=iso(T+day*86400),direction=direction,
                        amount=amount,fee=fee,asset='BTC',raw_ref='synthetic',**extra)
        x={'chain':'BTC','address':'synthetic','fetched_at':iso(T+40*86400),
           'coverage':{'complete':True,'to_time':iso(T+40*86400)},
           'txs':[tx(-10,'in','100'),tx(0,'out','30','1'),tx(5,'in','20'),
                  tx(8,'out','100','1',success=False),tx(9,'self','999','1'),tx(10,'out','0.1')],
           'balance_now':[{'asset':'BTC','amount':'86.9','raw_ref':'synthetic','as_of':iso(T+40*86400)}]}
        r=analyze(x,meta,ROOT/'synthetic')
        assert r['checkpoints']['T']['assets'][0]['native']=='100'
        assert r['checkpoints']['T+7d']['assets'][0]['native']=='89'
        assert abs(r['share_T_balance_gone']['T+7d']-0.11)<1e-12
        assert r['first_outflow_lag_days']==-0.5 and r['moved_after'] is True
        assert r['total_inflow_after_usd']==40 and r['moved_before'] is False
        assert r['checkpoints']['T+365d']['recognised_assets_usd']['value'] is None
        assert r['quality']['dust_after_rows']==1
        cp,recon,examples=pack_detail(r)
        full_cp,full_recon,full_examples=unpack_detail(cp,recon,examples)
        assert full_cp==r['checkpoints'] and full_recon==r['reconciliation'] and full_examples==r['examples']
        x['coverage']['complete']=False
        r=analyze(x,meta,ROOT/'synthetic')
        assert r['balance_at_designation_usd'] is None and r['still_there_today_usd']==173.8
        assert r['moved_before'] is None and r['moved_after'] is True and r['total_inflow_after_usd'] is None
        x['coverage']['complete']=True; x['balance_now'][0]['amount']='90'
        r=analyze(x,meta,ROOT/'synthetic')
        assert r['balance_at_designation_usd'] is None and r['reconciliation'][0]['pass'] is False
        # Fake ticker cannot authorize valuation; fee-only rows still debit coin.
        assert identity('ETH',{'asset':'0x123','symbol':'USDT','decimals':6})==('0x123',None)
        assert identity('ETH',{'asset':'0xdac17f958d2ee523a2206206994597c13d831ec7','decimals':18})[1] is None
        class PartialTimeline:
            suffix='.gz'
            def resolve(self): return ROOT/'synthetic-partial.json.gz'
            def read_bytes(self): return b'partially written gzip'
        data,entry=read_timeline(PartialTimeline())
        assert data is None and entry['status']=='unreadable_or_partial'
        # Missing native state must not become a zero native balance.
        x['txs']=[]; x['balance_now']=[]
        r=analyze(x,meta,ROOT/'synthetic')
        assert r['still_there_today_usd'] is None and r['balance_at_designation_usd'] is None
        print('PASS: boundaries, fees, failed/self transactions, dust, missing state/history, reconciliation, future checkpoints, identity, partial gzip, lossless CSV detail')
    finally: quote=original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['loader','balances','aggregates'], default='aggregates')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--aggregate-saved', action='store_true',help='Build aggregates from the saved balance CSV; does not refresh timelines')
    args = parser.parse_args()
    if args.self_test: self_test(); return 0
    if args.aggregate_saved and args.check: parser.error('--check always recomputes raw timelines; omit --aggregate-saved')
    snapshot=json.loads(OUT.read_text()) if args.check else None
    result = load_saved() if args.aggregate_saved else load(args.stage, save_progress=not args.check,snapshot=snapshot)
    text = csv_text(result) if args.stage!='loader' else None
    if text is not None: result['address_summary_sha256']=hashlib.sha256(text.encode()).hexdigest()
    if args.stage=='aggregates': aggregates(result)
    from scripts.lib.fetch_status import apply_status, report_status
    result=apply_status(result,ROOT,"checkpoints")
    document=report_status(report(result),result)
    compact_result(result)
    if args.check:
        old = json.loads(OUT.read_text())
        for x in (old, result): x.pop('generated_at_utc', None)
        csv_same=text is None or hashlib.sha256(CSV.read_bytes()).hexdigest()==result['address_summary_sha256']
        # Compare the published JSON representation: registry pairs are tuples
        # in Python and arrays after JSON serialization.
        json_same=json.dumps(old,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False)
        if not json_same or not csv_same:
            print('DIFF: saved inputs or results changed; rerun to refresh the provisional snapshot')
            before={r['path']:r.get('sha256') for r in old.get('timeline_manifest',[])}
            after={r['path']:r.get('sha256') for r in result.get('timeline_manifest',[])}
            print(json.dumps({'changed_timeline_files':sum(before.get(k)!=after.get(k) for k in before.keys()|after.keys()),
                'changed_other_inputs':[k for k in old.get('input_hashes',{}) if old['input_hashes'][k]!=result.get('input_hashes',{}).get(k)],
                'csv_reproduced':csv_same,
                'differing_result_sections':[k for k in old.keys()|result.keys() if json.dumps(old.get(k),sort_keys=True)!=json.dumps(result.get(k),sort_keys=True)]},sort_keys=True))
            return 1
        print('PASS: saved result and address CSV reproduced offline')
        return 0
    encoded=json.dumps(result, separators=(',', ':'), allow_nan=False)+'\n'
    if len(encoded.encode())>=5*1024*1024: raise RuntimeError('Summary must stay below 5 MB')
    if text is not None: atomic(CSV,text)
    atomic(OUT,encoded)
    atomic(DOC,document)
    print(json.dumps(result['coverage'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
