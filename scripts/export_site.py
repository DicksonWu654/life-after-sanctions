#!/usr/bin/env python3
"""Export evidence-backed static JSON; unavailable observations remain null.

Only site/data is written. All detail rows retain source and raw references.
"""
from __future__ import annotations
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import datetime as dt
import fcntl
import heapq
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lib.pipeline_io import ROOT, Generation, atomic, atomic_copy, digest, read_json, rows
from scripts.lib.site_export_io import json_bytes, write_json, compare_exports
from scripts.lib import published_inputs
from scripts.analysis.flows import token_asset
from scripts.analysis.checkpoints import unpack_detail
from scripts.analysis.inflows import asset_identity as inflow_asset_identity
from scripts.lib.site_enrichment import (InflowIndex, event_identity, quantity, valuation_fields,
    enrich_headlines, sankey_cohorts, slim_freezes, slim_amount, extra_cases, compact_case, compact_detail)

UTC = dt.timezone.utc
ET_ZONE = ZoneInfo('America/New_York')
DISCLAIMER = ('Research, not legal or compliance advice. Received funds from a sanctioned address is a factual '
               'on-chain statement, not an accusation. Exchanges may have frozen or reported funds. Labels are leads. '
               'No outflow found means within the data checked. Unknown observations are not zero.')
PROGRAM_LABELS = {
    'CAATSA - RUSSIA':'Russia (CAATSA)', 'CYBER2':'Cyber-related sanctions (CYBER2)',
    'CYBER3':'Cyber-related sanctions (CYBER3)', 'CYBER4':'Cyber-related sanctions (CYBER4)',
    'DPRK2':'North Korea (DPRK2)', 'DPRK3':'North Korea (DPRK3)', 'DPRK4':'North Korea (DPRK4)',
    'ELECTION-EO13848':'Election interference', 'FTO':'Foreign terrorist organizations',
    'HRIT-IR':'Iran human rights', 'IFSR':'Iranian financial sanctions',
    'ILLICIT-DRUGS-EO14059':'Illicit drugs', 'IRAN':'Iran', 'IRAN-EO13902':'Iran (key sectors)',
    'IRGC':'Islamic Revolutionary Guard Corps', 'NPWMD':'Weapons of mass destruction proliferation',
    'RUSSIA-EO14024':'Russia (harmful activities)', 'SDGT':'Global terrorism',
    'SDNTK':'Foreign narcotics kingpins', 'TCO':'Transnational criminal organizations',
    'UKRAINE-EO13661':'Ukraine-related sanctions',
}
PROGRAM_LABEL_SOURCE = 'https://ofac.treasury.gov/sanctions-programs-and-country-information'

def timestamp(value):
    if not value: return None
    try:
        t = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)
    except (ValueError, TypeError): return None

def designation(value):
    if not value: return None
    return dt.datetime.fromisoformat(value[:10]).replace(tzinfo=ET_ZONE).astimezone(UTC)

def iso(t): return t.isoformat().replace('+00:00', 'Z') if t else None

def number(value, unit, valued_at=None):
    out = {'value': value, 'unit': unit}
    if unit == 'usd': out['valued_at'] = valued_at
    return out

def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError): return None

def display_usd(value):
    """Six decimal places are ample for displayed USD estimates; retain tiny nonzeros."""
    if value is None: return None
    rounded = round(value,6)
    return rounded if rounded or value == 0 else float(format(value,'.8g'))

def publication_lag(listed, point):
    """Do not turn an uncertain same-day noon proxy into a before/after claim."""
    if point is None or not listed: return point, None
    date=dt.date.fromisoformat(listed[:10])
    noon=dt.datetime.combine(date,dt.time(12),ET_ZONE).astimezone(UTC)
    event=noon+dt.timedelta(days=point)
    start=designation(listed)
    end=designation((date+dt.timedelta(days=1)).isoformat())
    bounds=[(event-end).total_seconds()/86400,(event-start).total_seconds()/86400]
    return (None if bounds[0]<=0<=bounds[1] else point), bounds

def parts(value): return [s.strip() for s in (value or '').split(';') if s.strip()]

def norm(address): return address.lower() if address.lower().startswith('0x') else address

def key(chain, address): return (chain.lower(), norm(address))

def explorer(chain, address='', tx=''):
    base = {'eth':'https://etherscan.io', 'arb':'https://arbiscan.io', 'bsc':'https://bscscan.com',
            'base':'https://basescan.org', 'op':'https://optimistic.etherscan.io', 'polygon':'https://polygonscan.com',
            'avax':'https://snowtrace.io', 'etc':'https://etc.blockscout.com', 'btc':'https://mempool.space',
            'trx':'https://tronscan.org/#', 'sol':'https://solscan.io', 'xrp':'https://livenet.xrpl.org',
            'ltc':'https://litecoinspace.org', 'bch':'https://bch1.trezor.io', 'bsv':'https://bsvbook.guarda.co',
            'dash':'https://dash1.trezor.io', 'doge':'https://doge1.trezor.io', 'btg':'https://btg1.trezor.io'}.get(chain)
    return base + ('/tx/' + tx if tx else '/address/' + address) if base else None

class Prices:
    def __init__(self, root): self.root, self.cache = root, {}
    def quote(self, asset, at):
        at = timestamp(at)
        if not asset or not at: return None
        symbol = {'POL':'MATIC-POL', 'MATIC':'MATIC-POL', 'MATIC/POL':'MATIC-POL'}.get(asset, asset)
        if symbol not in self.cache:
            self.cache[symbol] = {}
            for frequency in ('1h', '1d'):
                data = rows(self.root / f'data/prices/{symbol}_{frequency}.csv.gz')
                data = sorted((timestamp(r['valuation_time_utc']), r) for r in data)
                self.cache[symbol][frequency] = ([t for t, _ in data], [r for _, r in data])
        for frequency, age in [('1h', dt.timedelta(hours=2)), ('1d', dt.timedelta(days=2))]:
            times, data = self.cache[symbol][frequency]
            pos = bisect_right(times, at) - 1
            if pos >= 0 and at-times[pos] <= age:
                return data[pos]
        return None
    def value(self, asset, amount, at):
        quote = self.quote(asset, at)
        if quote is None or finite(amount) is None: return None
        return {'value': finite(amount)*float(quote['price_usd']), 'unit':'usd',
                'valued_at':quote['valuation_time_utc'], 'price_raw_ref':quote['raw_ref'], 'source_url':quote['source_url']}

def identity(chain, event):
    asset, _ = token_asset(chain.upper(), event)
    if chain == 'sol':
        asset = {'SOL':'SOL', 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v':'USDC',
                 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB':'USDT'}.get(event.get('asset'))
    return asset

def countries(root, missing):
    """Country links come only from the official entity's saved XML fields."""
    mapping = {'Iran':'IRN', 'Russia':'RUS', 'Korea, North':'PRK', 'North Korea':'PRK',
               'China':'CHN', 'United States':'USA', 'Korea, South':'KOR', 'Vietnam':'VNM',
               'Laos':'LAO', 'Syria':'SYR', 'Taiwan':'TWN', 'United Kingdom':'GBR',
               'Czech Republic':'CZE', 'United Arab Emirates':'ARE', 'Venezuela':'VEN'}
    mapping.update({'Bahamas, The':'BHS','Burma':'MMR','Congo, Democratic Republic of the':'COD',
                    'Congo, Republic of the':'COG','Cote d Ivoire':'CIV','Curacao':'CUW',
                    'Macau':'MAC','Man, Isle of':'IMN','North Macedonia, The Republic of':'MKD',
                    'The Gambia':'GMB','Turkey':'TUR'})
    standard = Path('/usr/share/iso-codes/json/iso_3166-1.json')
    if standard.exists():
        for r in read_json(standard)['3166-1']:
            for name in ('name', 'official_name', 'common_name'):
                if name in r: mapping[r[name]] = r['alpha_3']
    manifest = read_json(root / 'data/raw/ofac/manifest.json', {})
    entry = manifest.get('sdn')
    out, regions = defaultdict(set), defaultdict(set)
    if not entry:
        missing['programs.country_links'] += 1
        return out, regions, None
    import gzip
    tree = ET.fromstring(gzip.decompress((root / entry['raw_ref']).read_bytes()))
    relevant_uids = {r['sdn_uid'] for r in rows(root/'data/ledger.csv') if r['sdn_uid']}
    for entity in tree:
        if entity.tag.rsplit('}', 1)[-1] != 'sdnEntry': continue
        uid = next((e.text for e in entity if e.tag.rsplit('}',1)[-1] == 'uid'), None)
        if uid not in relevant_uids: continue
        for e in entity.iter():
            if e.tag.rsplit('}',1)[-1] == 'country' and e.text:
                if e.text.startswith('Region:'): regions[uid].add(e.text.removeprefix('Region:').strip())
                elif e.text in mapping: out[uid].add(mapping[e.text])
                else: missing['programs.unmapped_country:' + e.text] += 1
    published = next((e.text for e in tree.iter() if e.tag.rsplit('}',1)[-1]=='Publish_Date'),None)
    published_date = dt.datetime.strptime(published,'%m/%d/%Y').date().isoformat() if published else None
    return out, regions, published_date

def generation_clock(root, input_snapshot=None):
    """Replay the published generation's clock, never the checking machine's clock."""
    previous = read_json(Path(root)/'site/data/meta.json', {})
    candidates = [((input_snapshot or {}).get('created_at_utc'), 'input_snapshot.created_at_utc')]
    candidates += [(previous.get(field), 'published_meta.'+field)
                   for field in ('generation_at_utc', 'exported_at_utc', 'last_refreshed_utc')]
    for value, basis in candidates:
        if timestamp(value):
            if basis == 'published_meta.generation_at_utc':
                basis = previous.get('generation_time_basis', basis)
            return timestamp(value), basis
    return None, 'missing; rebuild to record an input generation timestamp'


class Exporter:
    def __init__(self, root, output, refreshed=None, source_status=None, input_snapshot=None):
        self.root, self.output = Path(root), Path(output)
        self.refreshed, self.source_status = refreshed, source_status
        self.generation_at, self.generation_time_basis = generation_clock(self.root, input_snapshot)
        self.prices = Prices(self.root)
        self.missing = Counter()
        if self.generation_at is None: self.missing['export.generation_at_utc'] += 1
        self.results = {p.stem:read_json(p) for p in sorted((self.root/'results').glob('*.json'))}
        self.inflow_index = InflowIndex(self.root)
        self.pre_week = {r['id'].lower() if r['id'].split(':',1)[1].startswith('0x') else r['id'].split(':',1)[0].lower()+':'+r['id'].split(':',1)[1]:r
                         for r in self.results.get('premove',{}).get('address_results',[])
                         if r['window_days']==7 and r['shift_days']==0}
        self.ledger = rows(self.root / 'data/ledger.csv')
        self.entity_names = defaultdict(set)
        for r in self.ledger:
            if r['sdn_uid'] and r['sdn_name']: self.entity_names[r['sdn_uid']].add(r['sdn_name'])
        self.by_key = defaultdict(list)
        for r in self.ledger: self.by_key[key(r['chain'], r['address_normalized'])].append(r)
        self.timeline_paths = {}
        for path in sorted((self.root / 'data/timelines').glob('*/*.json*')):
            if path.name.endswith(('.json', '.json.gz')):
                self.timeline_paths[key(path.parent.name, path.name.split('.json')[0])] = path
        self.freeze_rows = defaultdict(list)
        self.matched_freezes = rows(self.root/'data/derived/freeze_match.csv')
        self.checkpoint_rows = {key(r['chain'],r['address']):r for r in rows(self.root/'data/derived/address_summary.csv') if r.get('view')=='listed_chain'}
        for r in rows(self.root / 'data/freezes.csv'):
            self.freeze_rows[key(r['chain'], r.get('address_normalized') or r['address'])].append(r)
        self.index, self.coverage, self.detail_summary = [], defaultdict(Counter), {}
        self.bytes = 0
        self.files = 0

    def emit(self, rel, obj):
        payload = json_bytes(obj)
        if len(payload) > 20_000_000: raise ValueError(f'{rel} exceeds per-file 20 MB budget')
        self.bytes += len(payload)
        self.files += 1
        atomic(self.output / rel, payload)

    def detail(self, source):
        chain, address = key(source['chain'], source.get('address_normalized') or source['address'])
        if not re.fullmatch(r'[a-z0-9_-]+', chain) or not re.fullmatch(r'[A-Za-z0-9:._-]+', address):
            raise ValueError('Unsafe chain/address path')
        ledger = self.by_key[(chain, address)]
        entities = {(r['sdn_uid'],r['sdn_name']) for r in ledger}
        # Address rows carry explicit OFAC entity UIDs even when a chain alias
        # has no exact ledger-row join. Resolve only those saved UIDs by name.
        for uid in parts(source.get('all_entity_uids') or source.get('sdn_uids')):
            entities.update((uid,name) for name in self.entity_names.get(uid,()))
        if not entities: self.missing['address.entities'] += 1
        listed = source.get('first_listed_date') or next((r['listed_date'] for r in ledger if r['listed_date']), '')
        when = designation(listed)
        row = {'id':chain+':'+address, 'chain':chain, 'address':address,
               'ticker':source.get('tickers') or ';'.join(sorted({r['ticker'] for r in ledger})),
               'entities':[{'uid':uid,'name':name} for uid,name in sorted(entities)],
               'programs':parts(source.get('programs')), 'listed':listed, 'delisted':source.get('delisted_date') or None,
               'trackable':source['trackable'].lower() == 'true', 'untrackable_reason':source.get('untrackable_reason') or None,
               'balance_at_listing_usd':None, 'balance_today_usd':None, 'moved_after':None,
               'moved_before_designation':None, 'first_outflow_days':None, 'frozen':False, 'flags':[],
               'assets_today':[], 'explorer_url':explorer(chain,address), 'source_url':source.get('source_url'),
               'raw_ref':source.get('raw_ref')}
        path = self.timeline_paths.get((chain, address))
        timeline = None
        if path:
            try: timeline = read_json(path)
            except (OSError, ValueError, EOFError): self.missing['address.unreadable_timeline'] += 1
        if not timeline: self.missing['address.timeline'] += 1
        cov = (timeline or {}).get('coverage', {})
        cc = self.coverage[chain]
        cc['addresses'] += 1
        cc['trackable'] += int(row['trackable'])
        cc['readable_histories'] += int(timeline is not None)
        cc['complete_histories'] += int(cov.get('complete') is True)
        events, raw_refs, sources, windows = [], set(parts(source.get('raw_ref'))), set(parts(source.get('source_url'))), []
        def refs(value, dest):
            if isinstance(value, str): dest.add(value)
            elif isinstance(value, list):
                for v in value: refs(v, dest)
        dates = set()
        if listed:
            dates.add(listed)
            if not ledger:
                events.append({'time':iso(when),'kind':'designation',
                               'source_url':source.get('source_url'),'raw_ref':source.get('raw_ref'),
                               'date_basis':'first_listed_date in data/addresses.csv; publication date start proxy'})
        for record in ledger:
            if record['listed_date']: dates.add(record['listed_date'])
            for event in json.loads(record.get('listing_events') or '[]'):
                if event.get('date'): dates.add(event['date'])
            if record['listed_date']:
                events.append({'time':iso(designation(record['listed_date'])), 'kind':'designation',
                               'source_url':record['listed_action_url'], 'raw_ref':record.get('listed_raw_ref')})
            if record.get('delisted_date'):
                events.append({'time':iso(designation(record['delisted_date'])), 'kind':'delisting',
                               'source_url':record.get('delisted_action_url'), 'raw_ref':record.get('delisted_raw_ref')})
        for d in dates:
            t = designation(d)
            windows.append((t-dt.timedelta(days=7), t+dt.timedelta(days=7)))
        txs = (timeline or {}).get('txs', [])
        newest, largest, protected, total, before, after, first_out, latest_in = [], [], set(), 0, False, False, None, None
        monthly = defaultdict(Counter)
        classifications = self.inflow_index.address(chain,address)
        def event_value(tx, index):
            joined=InflowIndex.match(classifications,tx,index) if tx.get('direction')=='in' else None
            asset=identity(chain,tx)
            if not asset:
                asset,recognised=inflow_asset_identity(chain.upper(),tx)
                if not recognised: asset=None
            value=self.prices.value(asset,tx.get('amount'),tx.get('time_utc') or tx.get('time') or tx.get('timestamp'))
            cls,rule,confidence=None,None,None
            if joined:
                cls=joined['inflow_class'] or None
                rule,confidence=joined['classification_rule'],joined['classification_confidence']
                if joined['usd']!='':
                    value={'value':finite(joined['usd']),'valued_at':joined['valued_at'],
                           'price_raw_ref':joined['price_raw_ref'],'source_url':'data/derived/inflows.csv'}
            elif value:
                cls='dust' if value['value']<1 else 'real'
                rule='recognized_asset_below_1_usd' if cls=='dust' else 'recognized_asset_at_least_1_usd'
                confidence='threshold_only; poisoning not independently tested outside the saved inflow index'
            return asset,value,cls,rule,confidence,joined
        for i, tx in enumerate(txs):
            t = timestamp(tx.get('time_utc') or tx.get('time') or tx.get('timestamp'))
            direction = tx.get('direction')
            valid = (direction in ('in','out') and tx.get('success') is not False and tx.get('is_transfer') is not False
                     and tx.get('confirmed') is not False
                     and tx.get('event_type') not in ('transaction_fee', 'balance_adjustment') and finite(tx.get('amount')) is not None)
            if not t or not valid: continue
            total += 1
            asset,valued,cls,rule,confidence,joined=event_value(tx,i)
            month=monthly[t.strftime('%Y-%m')]
            month[direction] += 1
            month['class_'+(cls or 'unknown')] += 1
            if valued: month['priced_'+direction+'_usd'] += valued['value']
            else: month['unpriced_'+direction] += 1
            item_value=(valued['value'] if valued else -1,t,i)
            if len(largest)<1000: heapq.heappush(largest,item_value)
            elif item_value>largest[0]: heapq.heapreplace(largest,item_value)
            if when and direction == 'out' and (finite(tx.get('amount')) or 0) > 0:
                if t >= when:
                    after = True
                    first_out = min(first_out, t) if first_out else t
                elif t >= when-dt.timedelta(days=7): before = True
            if when and direction == 'in' and t >= when and (finite(tx.get('amount')) or 0) > 0:
                latest_in = max(latest_in, t) if latest_in else t
            if any(lo <= t <= hi for lo,hi in windows): protected.add(i)
            item = (t, i)
            if len(newest) < 2000: heapq.heappush(newest, item)
            elif item > newest[0]: heapq.heapreplace(newest, item)
        candidate_indices=protected | {i for _,i in newest} | {i for _,_,i in largest}
        for i in candidate_indices:
            tx = txs[i]
            time = tx.get('time_utc') or tx.get('time') or tx.get('timestamp')
            asset,valued,cls,rule,confidence,joined=event_value(tx,i)
            if not valued: self.missing['address.events.usd'] += 1
            counterparties = tx.get('counterparties') or []
            event = {'time':time, 'kind':tx['direction'], 'asset':asset or tx.get('asset') or tx.get('symbol'),
                     'amount':finite(tx.get('amount')), 'usd':display_usd(valued['value']) if valued else None,
                     'valued_at':valued['valued_at'].replace('T00:00:00Z','') if valued else None, 'counterparty':counterparties[0] if len(counterparties)==1 else None,
                     'counterparty_label':tx.get('counterparty_label'), 'label_source':tx.get('label_source'),
                     'tx':tx.get('hash') or tx.get('tx_hash'),
                     'class':cls, 'classification_rule':rule, 'classification_confidence':confidence}
            if joined:
                event['event_id']=joined['event_id']
                event['classification_ref']='data/derived/inflows.csv#event_id='+joined['event_id']
            event['explorer_url'] = explorer(chain, tx=event['tx']) if event['tx'] else None
            if valued: raw_refs.add(valued['price_raw_ref'].split('#',1)[0])
            events.append({k:v for k,v in event.items() if v is not None})
        relevant_freezes = sorted(self.freeze_rows[(chain,address)], key=lambda r:(int(r.get('block') or 0),int(r.get('log_index') or 0)))
        states = {}
        for r in relevant_freezes:
            kind = 'burn' if 'Destroyed' in r['event'] else 'unfreeze' if r['event'] in ('RemovedBlackList','UnBlacklisted','Unblacklisted') else 'freeze'
            if kind != 'burn': states[r['token']] = kind == 'freeze'
            valued = self.prices.value(r['token'], r.get('amount') if kind=='burn' else r.get('balance_at_freeze'), r['timestamp'])
            events.append({'time':r['timestamp'],'kind':kind,'asset':r['token'],
                'amount':finite(r.get('amount') if kind=='burn' else r.get('balance_at_freeze')),
                'usd':valued['value'] if valued else None,'valued_at':valued['valued_at'] if valued else None,
                'tx':r['tx_hash'],'explorer_url':r['source_url'],'source_url':r['source_url'],'raw_ref':r['raw_ref']})
        row['frozen'] = any(states.values())
        if timeline and when:
            row['moved_after'] = True if after else False if cov.get('complete') is True else None
            row['moved_before_designation'] = True if before else False if cov.get('complete') is True else None
            if first_out: row['first_outflow_days'] = (first_out-when).total_seconds()/86400
        if before: row['flags'].append('moved_before_designation')
        # A past payment alone does not establish that an address is still receiving.
        if (latest_in and self.generation_at and
                dt.timedelta(0) <= self.generation_at-latest_in < dt.timedelta(days=31)):
            row['flags'].append('still_receiving')
        if timeline and cov.get('complete') is not True: row['flags'].append('partial_history')
        if not listed: row['flags'].append('unknown_designation_date')
        as_of = (timeline or {}).get('balance_checked_at') or (timeline or {}).get('fetched_at')
        for balance in (timeline or {}).get('balance_now', []):
            amount = finite(balance.get('amount'))
            asset = identity(chain, balance)
            at = balance.get('as_of') or balance.get('reported_at') or as_of
            valued = self.prices.value(asset, amount, at)
            row['assets_today'].append({'asset':asset or balance.get('asset'), 'native':amount,
                'usd':valued['value'] if valued else None, 'valued_at':valued['valued_at'] if valued else None,
                'balance_observed_at':at,'raw_ref':balance.get('raw_ref'), 'price_raw_ref':valued.get('price_raw_ref') if valued else None})
        assets = row['assets_today']
        if assets and all(a['usd'] is not None for a in assets):
            row['balance_today_usd'] = number(sum(a['usd'] for a in assets),'usd',sorted({a['valued_at'] for a in assets}))
        else: self.missing['address.balance_today_usd'] += 1
        self.missing['address.balance_at_listing_usd'] += 1
        checkpoints = []
        for label, days in [('T-7d',-7),('T',0),('T+7d',7),('T+30d',30),('T+365d',365)]:
            checkpoints.append({'label':label,'time':iso(when+dt.timedelta(days=days)) if when else None,
                                'balances':[], 'missing':'Historical balance analysis not available; no zero imputed.'})
        checkpoints.append({'label':'today', 'time':as_of, 'balances':assets})
        observed = self.checkpoint_rows.get((chain,address))
        if observed:
            packed = json.loads(observed['checkpoints'])
            unpacked, _, examples = unpack_detail(packed, json.loads(observed['reconciliation']),json.loads(observed['examples']))
            observed_checkpoints = {label:{'label':label,'time':cp.get('time_utc'),
                'balances':[{'asset':a.get('symbol') or a['asset'],'native':finite(a.get('native')),
                             'usd':a.get('usd'),'valued_at':a.get('valued_at'),'raw_ref':a.get('raw_ref'),
                             'price':a.get('price'),'method':a.get('method')} for a in cp.get('assets',[])]}
                           for label,cp in unpacked.items()}
            checkpoints = [observed_checkpoints.get(cp['label'],cp) for cp in checkpoints]
            for field,column,label in [('balance_at_listing_usd','balance_at_designation_usd','T'),
                                       ('balance_today_usd','still_there_today_usd','today')]:
                value = finite(observed.get(column))
                row[field] = number(value,'usd',unpacked.get(label,{}).get('time_utc')) if value is not None else None
            row['moved_after'] = {'True':True,'False':False}.get(observed.get('moved_after'))
            row['moved_before_designation'] = {'True':True,'False':False}.get(observed.get('moved_before'))
            before_proxy=finite(observed.get('last_outflow_before_lag_days'))
            row['last_outflow_before_days']=before_proxy
            _,row['last_outflow_before_interval_days']=publication_lag(listed,before_proxy)
            pre_event=examples.get('last_outflow_before')
            row['last_outflow_before_tx']={k:v for k,v in pre_event.items() if k in ('chain','hash','time_utc','explorer_url','raw_ref','amount')} if pre_event else None
            proxy=finite(observed.get('first_outflow_lag_days'))
            row['first_outflow_days'],row['first_outflow_lag_interval_days']=publication_lag(listed,proxy)
            row['first_outflow_after_days']=proxy
            if proxy is not None:
                row['first_outflow_days_proxy']=proxy
                row['first_outflow_lag_basis']='Noon ET point with full listing-day uncertainty; exact publication time unavailable.'
                if row['first_outflow_days'] is None: row['flags'].append('publication_day_order_unknown')
            row['flags'] = [f for f in row['flags'] if f!='moved_before_designation']
            if row['moved_before_designation']: row['flags'].append('moved_before_designation')
            row['balance_scope'] = 'Recognised assets only; reconciliation and omitted assets in checkpoint evidence.'
            raw_refs.add('data/derived/address_summary.csv')
            if row['balance_at_listing_usd']: self.missing['address.balance_at_listing_usd'] -= 1
        eligible=self.pre_week.get(row['id'])
        row['pre_week_test']={'eligible':eligible is not None,
            'active':bool(eligible['tests']['any_outflow']['real']) if eligible else None,
            'source_url':'results/premove.json','window_days':7}
        early=[r for r in self.matched_freezes if key(r['chain'],r['address'])==(chain,address) and r['listing_relation']=='OFAC-listed chain' and finite(r.get('lag_upper_hours')) is not None]
        row['frozen_before_listing_day']=any(float(r['lag_upper_hours'])<0 for r in early)
        for event in events:
            refs(event.get('raw_ref'), raw_refs)
            refs(event.get('price_raw_ref'), raw_refs)
            refs(event.get('source_url'), sources)
        for asset in assets:
            refs(asset.get('raw_ref'),raw_refs); refs(asset.get('price_raw_ref'), raw_refs)
        if path: raw_refs.add(str(path.relative_to(self.root)))
        row['assets_today'] = [{k:a[k] for k in ('asset','native','usd','valued_at')} for a in assets if a['usd'] is not None]
        row['unpriced_assets_today_count']=sum(a['usd'] is None for a in assets)
        row['unpriced_assets_ref']=str(path.relative_to(self.root))+'#/balance_now' if path and row['unpriced_assets_today_count'] else None
        # Deduplicate designation rows repeated across entity UIDs.
        events = list({json.dumps(e,sort_keys=True):e for e in events}.values())
        events.sort(key=lambda e:e.get('time') or '', reverse=True)
        detail = dict(row, checkpoints=checkpoints, events=events, sources=sorted(sources), raw_refs=sorted(raw_refs),
                      monthly_counts=[dict(month=month,raw_ref=str(path.relative_to(self.root))+'#/txs' if path else None,
                          **{k:round(v,6) if 'usd' in k else v for k,v in count.items()}) for month,count in sorted(monthly.items())],
                      monthly_counts_units={'in':'events','out':'events','class_*':'events','priced_*_usd':'usd at each transfer time; known subtotal','unpriced_*':'events'},
                      monthly_counts_scope='All valid saved transfer events before display truncation; fee-only/failed/unconfirmed/non-transfer rows excluded by the exporter. Source coverage limits still apply.',
                      coverage={k:v for k,v in cov.items() if k in ('complete','from_block','from_time','to_block','to_time','checked_through_time')},
                      coverage_ref=str(path.relative_to(self.root))+'#/coverage' if path else None,
                      usd_display_precision='6 decimal places; tiny positive values retain 8 significant figures; source prices and quantities remain in saved evidence',
                      truncation={'truncated':total>len(candidate_indices),
                          'observed_transfer_events':total,'retained_transfer_events':len(candidate_indices),
                          'observed_designation_window_transfers':len(protected),
                          'rule':'2,000 newest transfers plus every T-7d through T+7d designation-window transfer, and all designation, delisting and issuer events.',
                          'designation_window_dates':sorted(dates)})
        detail['_key_transfer_hashes']=[event.get('hash') for event in ((examples.get('largest_outflows',[])+examples.get('largest_inflows',[])+[examples.get('first_outflow'),examples.get('last_outflow_before')]) if observed else []) if event]
        valuation_fields(detail)
        compact_detail(detail)
        self.emit(f'address/{chain}/{address}.json',detail)
        self.index.append(row)
        self.detail_summary[row['id']] = {'events':[e for e in events if e['kind'] in ('designation','delisting','freeze','burn')],
                                          'first_outflow':first_out, 'sources':sorted(sources)}

    def freezes(self):
        joined = read_json(self.root/'results/freeze_match.json',{})
        if self.matched_freezes and joined:
            points = []
            for r in self.matched_freezes:
                if r.get('listing_relation') != 'OFAC-listed chain' or r.get('blacklisted_ever')!='true': continue
                points.append({'issuer':r['issuer'],'chain':r['chain'].lower(),'address':r['address'],
                    'lag_hours':finite(r['lag_hours']), 'lag_hours_interval':[finite(r['lag_lower_hours']),finite(r['lag_upper_hours'])],
                    'lag_basis':r['T_pub_precision'],'amount_frozen':json.loads(r['freeze_balance_usd']) if r.get('freeze_balance_usd') else None,
                    'burned':int(r.get('burn_event_count') or 0)>0,'ofac_action_date':r['first_listed_date'],
                    'freeze_tx':r['first_blacklist_tx'],'source_url':r['first_blacklist_source_url'],'raw_ref':json.loads(r['raw_ref'])})
            summary=[]
            for r in joined.get('summary',[]):
                if r.get('variant')!='all' or r.get('program')!='ALL' or r.get('year')!='ALL': continue
                summary.append({'issuer':r['issuer'],'chain':r['chain'].lower(),
                    'sanctioned_addresses_holding_token':r['observed_holders_at_T_or_after'],
                    'frozen':r['blacklisted_ever'],'share_frozen':r['share_frozen_all_addresses'],
                    'all_ofac_chain_addresses':r['all_ofac_chain_addresses'],
                    'frozen_observed_holders':r['frozen_observed_holders'],
                    'share_frozen_observed_holders':r['share_frozen_observed_holders'],
                    'definitely_before_publication':r['definitely_before_publication'],
                    'before_listing_day':r['definitely_before_publication'],
                    'median_lag_interval_lower_hours':r['median_lag_interval_lower_hours'],
                    'median_lag_interval_upper_hours':r['median_lag_interval_upper_hours'],
                    'median_lag_hours':r['median_lag_hours'],'p90_lag_hours':r['p90_lag_hours'],
                    'usd_frozen':slim_amount(r['usd_frozen_known_subtotal']),
                    'share_frozen_denominator':'all_ofac_chain_addresses',
                    'notes':'share_frozen uses all OFAC chain-address pairs, including unknown/invalid token holders. The separate observed-holder share uses only observed holders. Known freeze USD subtotal only; native coin is not blacklisted.'})
            self.missing['freezes.amount_frozen_usd'] = sum(
                p['amount_frozen'] is None or p['amount_frozen'].get('value') is None for p in points)
            self.emit('freezes_evidence.json',{':'.join((p['issuer'],p['chain'],p['address'])):p for p in points})
            self.emit('freezes.json',{'points':slim_freezes(points),'summary':valuation_fields(summary),
                'source_url':'results/freeze_match.json','raw_ref':'data/derived/freeze_match.csv','evidence_ref':'freezes_evidence.json'})
            return
        points, summary = [], []
        for row in self.index:
            records = sorted(self.freeze_rows[key(row['chain'],row['address'])], key=lambda r:r['timestamp'])
            for token in sorted({r['token'] for r in records}):
                additions = [r for r in records if r['token']==token and r['event'] in ('AddedBlackList','Blacklisted')]
                if not additions or not row['listed']: continue
                r = additions[0]
                start = designation(row['listed'])
                end = designation((dt.date.fromisoformat(row['listed'])+dt.timedelta(days=1)).isoformat())
                lag = (timestamp(r['timestamp'])-start).total_seconds()/3600
                valued = self.prices.value(token,r.get('balance_at_freeze'),r['timestamp'])
                if not valued: self.missing['freezes.amount_frozen_usd'] += 1
                points.append({'issuer':'tether' if token=='USDT' else 'circle','chain':row['chain'],
                    'address':row['address'],'lag_hours':lag,'lag_hours_interval':[(timestamp(r['timestamp'])-end).total_seconds()/3600,lag],
                    'lag_basis':'relative to start of OFAC publication date in America/New_York; actual publication time unknown',
                    'amount_frozen':valued,'burned':any(x['event']=='DestroyedBlackFunds' for x in records if x['token']==token),
                    'ofac_action_date':row['listed'],'freeze_tx':r['tx_hash'],'raw_ref':r['raw_ref'],'source_url':r['source_url']})
        for issuer,chain in sorted({(p['issuer'],p['chain']) for p in points}):
            ps = [p for p in points if p['issuer']==issuer and p['chain']==chain]
            lags = sorted(p['lag_hours'] for p in ps)
            summary.append({'issuer':issuer,'chain':chain,'sanctioned_addresses_holding_token':None,
                'frozen':number(len(ps),'addresses'),'share_frozen':None,
                'median_lag_hours':number((lags[(len(lags)-1)//2]+lags[len(lags)//2])/2,'hours'),
                'p90_lag_hours':number(lags[math.ceil(len(lags)*.9)-1],'hours'),'usd_frozen':None,
                'notes':'First observed blacklist event per ledger chain-address/token. Token-holder denominator and most historical balances unavailable; lags use date-start proxies.'})
        self.missing['freezes.token_holder_denominators'] += 1
        self.emit('freezes.json',{'points':points,'summary':summary})

    def analyses(self):
        results = self.results
        headline = []
        for name,result in results.items():
            candidates = result.get('findings') or result.get('headline_candidates') or result.get('candidate_findings') or []
            for i,c in enumerate(candidates):
                big = c.get('big') or c.get('amount') or c.get('number') or c.get('after') or c.get('metric')
                if not isinstance(big,dict) or finite(big.get('value')) is None: continue
                headline.append({'id':c.get('id',name+'-'+str(i)), 'big':big, 'sentence':c.get('sentence') or c.get('statement') or c.get('headline') or c.get('title') or '',
                                 'detail_md':c.get('confidence') or result.get('interpretation') or 'Provisional; see the saved analysis coverage.',
                                 'example_txs':c.get('example_txs') or c.get('examples') or [], 'finding_ref':'results/'+name+'.json',
                                 'raw_ref':c.get('raw_ref') or result.get('input_snapshot') or result.get('snapshot_ref')})
        if not headline: self.missing['headline.analysis_candidates'] += 1
        self.emit('headline.json',enrich_headlines(headline,results))
        flows = results.get('flows',{})
        graph = flows.get('sankey',{})
        nodes, links = {}, []
        for view in ('program','chain'):
            g = graph.get(view,{})
            for node in g.get('nodes',[]): nodes[node['id']] = node
            links.extend(g.get('links',[]))
        exported_graph={'unit':'usd','valued_at':'at transfer time','nodes':list(nodes.values()),'links':links,
            'hop_rule':flows.get('trace',{}).get('hop_rule','No flow analysis available.'),
            'notes':'Program and chain link sets are alternative views of the same dollars; never sum them. Gross transfers can recirculate. Public labels are leads. '+ ' '.join(flows.get('notes',[])),
            'source_url':'results/flows.json','raw_ref':flows.get('snapshot_ref')}
        exported_graph=sankey_cohorts(self.root,exported_graph,self.entity_names,flows)
        if exported_graph.get('cohort_split_missing'): self.missing['sankey.cohort_split'] += 1
        self.emit('sankey.json',valuation_fields(exported_graph))
        if not flows: self.missing['sankey.analysis'] += 1
        return results

    def cases(self):
        result = self.results.get('cases',{})
        if result.get('cases'):
            cases=result['cases']+extra_cases(self.index,self.matched_freezes,self.checkpoint_rows,self.results.get('freeze_match',{}))
            self.emit('cases_evidence.json',{case['id']:case for case in cases})
            self.emit('cases.json',[compact_case(case) for case in cases])
            return
        groups = defaultdict(list)
        for r in self.index:
            for entity in r['entities']: groups[(entity['uid'],entity['name'])].append(r)
        preferred = ['TORNADO','GARANTEX','SUEX','CHATEX','BLENDER','SINBAD','LAZARUS','HYDRA','PRINCE','SECONDEYE']
        ordered = sorted(groups, key=lambda k:(next((i for i,x in enumerate(preferred) if x in k[1].upper()),100),-len(groups[k]),k))
        cases = []
        for uid,name in ordered[:10]:
            group = groups[(uid,name)]
            first = min((r['listed'] for r in group if r['listed']), default='')
            ledger = [r for r in self.ledger if r['sdn_uid']==uid]
            events = []
            for r in group:
                detail = self.detail_summary[r['id']]
                for e in detail['events']:
                    events.append({'date':e['time'],'kind':e['kind'],'label':e['kind'].capitalize()+' '+r['address'],
                                   'source_url':e.get('source_url') or e.get('explorer_url'), 'raw_ref':e.get('raw_ref')})
                if detail['first_outflow']:
                    events.append({'date':iso(detail['first_outflow']),'kind':'first_outflow','label':'Observed outflow on '+r['chain'],
                                   'source_url':r['explorer_url'],'raw_ref':'site/data/address/'+r['chain']+'/'+r['address']+'.json'})
            contexts = rows(self.root/'data/reference/cases.csv')
            context = next((c for c in contexts if name.upper() in c['name'].upper() or c['name'].upper() in name.upper()),None)
            cases.append({'id':uid or re.sub('[^a-z0-9]+','-',name.lower()),'name':name,
                'program':'; '.join(sorted({p for r in group for p in r['programs']})), 'designated':first,
                'press_release_url':context['treasury_press_release_url'] if context else next((r['listed_action_url'] for r in ledger if r['listed_action_url']),None),
                'chains':sorted({r['chain'] for r in group}), 'one_liner':context['why_famous'] if context else 'OFAC-named entity; observed address events and source coverage are below.',
                'addresses':[r['id'] for r in group], 'events':sorted(events,key=lambda e:e['date']),
                'today':{'balance_usd':None,'status_sentence':'Balance coverage varies by address and asset; inspect the address timeline.',
                         'covers':'Listed chain-address pairs only. Entity totals withheld until historical checkpoint analysis is available.'}})
        self.emit('cases.json',cases)

    def run(self):
        for row in rows(self.root/'data/addresses.csv'): self.detail(row)
        self.missing['address.balance_at_listing_usd'] = sum(r['balance_at_listing_usd'] is None for r in self.index)
        self.missing['address.balance_today_usd'] = sum(r['balance_today_usd'] is None for r in self.index)
        if len(self.index) != len(self.by_key): raise ValueError('Address index does not cover every ledger chain-address pair')
        self.emit('addresses.json',self.index)
        self.freezes()
        results = self.analyses()
        self.cases()
        country_map, regions, publication = countries(self.root,self.missing)
        programs = []
        for program in sorted({p for r in self.index for p in r['programs']}):
            group = [r for r in self.index if program in r['programs']]
            countries_count = Counter(c for r in group for c in {c for e in r['entities'] for c in country_map[e['uid']]})
            observed_T = [r['balance_at_listing_usd'] for r in group if r['balance_at_listing_usd']]
            observed_today = [r['balance_today_usd'] for r in group if r['balance_today_usd']]
            movement = [r['moved_after'] for r in group if r['moved_after'] is not None]
            if program not in PROGRAM_LABELS: self.missing['programs.label'] += 1
            programs.append({'program':program,'label':PROGRAM_LABELS.get(program,program),
                'label_source_url':PROGRAM_LABEL_SOURCE,'countries':sorted(countries_count),
                'regions':sorted({region for r in group for e in r['entities'] for region in regions[e['uid']]}),
                'country_addresses':dict(countries_count),'addresses':number(len(group),'addresses'),
                'entities':number(len({e['uid'] for r in group for e in r['entities'] if e['uid']}),'entities'),
                'value_at_designation_usd':number(sum(r['value'] for r in observed_T),'usd','each address at its own T; known recognised assets subtotal') if observed_T else None,
                'value_today_usd':number(sum(r['value'] for r in observed_today),'usd','each address latest saved observation; known recognised assets subtotal') if observed_today else None,
                'share_moved_after':number(sum(movement)/len(movement),'share') if movement else None,
                'denominators':{'value_at_designation_addresses':len(observed_T),'value_today_addresses':len(observed_today),'movement_observed_addresses':len(movement)},
                'source_url':'data/ledger.csv','raw_ref':sorted({r['raw_ref'] for r in group if r['raw_ref']})})
        self.emit('programs.json',programs)
        self.missing['programs.balance_or_movement_fields'] += sum(
            any(p[k] is None for k in ('value_at_designation_usd','value_today_usd','share_moved_after')) for p in programs)
        previous = read_json(self.root/'site/data/meta.json',{})
        statuses = self.source_status if self.source_status is not None else previous.get('source_status',{})
        coverage = []
        for chain,counts in sorted(self.coverage.items()):
            source = 'evm' if chain in ('eth','arb','bsc','polygon','op','base','avax','etc') else 'tron' if chain=='trx' else 'utxo' if chain in ('btc','bch','bsv','ltc','dash','doge','zec','btg','xvg') else 'other'
            state = statuses.get(source,{})
            required_sources=[source,'ledger','prices']+(['freezes'] if chain in ('eth','trx') else [])
            stale_sources=sorted(s for s in required_sources if statuses.get(s,{}).get('stale',True))
            coverage.append(dict(counts,chain=chain,complete_history=counts['complete_histories']==counts['addresses'],
                stale=state.get('stale',True),source=source,
                stale_sources=stale_sources,
                notes=f"{counts['readable_histories']} saved histories; {counts['complete_histories']} marked complete by provider. " +
                      ('Source refresh stale: '+state.get('reason','not yet refreshed by pipeline') if state.get('stale',True) else 'See per-address coverage for asset and history limits.')))
        before_ids={r['id'] for r in self.index if r['moved_before_designation'] is True}
        freeze_ids={r['id'] for r in self.index if r['chain']=='trx' and r['frozen_before_listing_day']}
        eligible=[r for r in self.index if r['pre_week_test']['eligible']]
        meta = {'schema_version':2,'last_refreshed_utc':self.refreshed or previous.get('last_refreshed_utc'),
            'exported_at_utc':iso(self.generation_at),
            'generation_at_utc':iso(self.generation_at),
            'generation_time_basis':self.generation_time_basis,
            'ofac_list_published_utc':publication,
            'counts':{'addresses':len(self.index),'entities':len({r['sdn_uid'] for r in self.ledger if r['sdn_uid']}),
                      'actions':len(rows(self.root/'data/actions.csv')),'chains':len(self.coverage),
                      'trackable_addresses':sum(r['trackable'] for r in self.index),
                      'untrackable_addresses':sum(not r['trackable'] for r in self.index)},
            'coverage':coverage,'source_status':statuses,'missing':dict(sorted(self.missing.items())),
            'movement_definitions':{
                'moved_before_designation':'checkpoints.moved_before: qualifying non-dust recognized-asset outgoing transfer in [T-7 days,T), T=00:00 ET. Coverage-aware boolean; not derived from issuer logs.',
                'first_outflow_days':'First qualifying outgoing transfer at/after T relative to noon ET T_pub, days. For backward compatibility the display point is null if its publication-day interval crosses zero. first_outflow_after_days supplies the signed noon proxy and first_outflow_lag_interval_days its uncertainty.',
                'last_outflow_before_days':'Last qualifying outgoing transfer at any checked time before T, relative to noon ET; may be much older than the 7-day flag. Source example and interval exported separately.',
                'pre_week_test':'Separate preregistered premove cohort: eligible complete non-Tornado histories with baseline windows; 7-day zero-shift activity and baseline use the saved premove method.',
                'frozen_before_listing_day':'First issuer blacklist event strictly before the start of the OFAC date; derived from freeze-match lag upper bound, independent of transfers.'},
            'movement_reconciliation':{
                'checkpoint_pre_week_movers':quantity(len(before_ids),'addresses'),
                'checkpoint_pre_week_by_chain':dict(Counter(r['chain'] for r in self.index if r['id'] in before_ids)),
                'tron_frozen_before_listing_day':quantity(len(freeze_ids),'addresses'),
                'intersection':quantity(len(before_ids&freeze_ids),'addresses'),
                'premove_eligible':quantity(len(eligible),'addresses'),
                'premove_active':quantity(sum(r['pre_week_test']['active'] is True for r in eligible),'addresses'),
                'checkpoint_movers_in_premove_cohort':quantity(sum(r['moved_before_designation'] is True for r in eligible),'addresses'),
                'checkpoint_movers_outside_premove_cohort':quantity(sum(r['id'] in before_ids and not r['pre_week_test']['eligible'] for r in self.index),'addresses'),
                'empty_when_listed':next((c['number'] for c in results.get('checkpoints',{}).get('findings',[]) if c.get('id')=='empty_when_listed'),None),
                'source_url':['results/checkpoints.json','results/premove.json','results/freeze_match.json'],
                'raw_ref':['data/derived/address_summary.csv','data/derived/freeze_match.csv']},
            'disclaimer_md':DISCLAIMER,'provisional':any(r.get('provisional',True) for r in results.values()) or any(v.get('stale',True) for v in statuses.values()),'export_script':'scripts/export_site.py',
            'analysis_sources':{name:{'path':'results/'+name+'.json','sha256':digest(self.root/'results'/f'{name}.json')} for name in results},
            'export_counts':{'files':self.files+1,'bytes_before_meta':self.bytes}}
        self.emit('meta.json',meta)
        return {'files':self.files,'bytes':self.bytes,'addresses':len(self.index),'missing_fields':dict(self.missing)}

def fit_budget(stage, budget=100_000_000):
    """Bound each address to 1.5 MB and the entire JSON export to 100 MB."""
    def size(): return sum(p.stat().st_size for p in stage.rglob('*.json'))
    paths=sorted((stage/'address').glob('*/*.json'))
    for cap in (2000,1500,1000,750,500,250,100,0):
        for path in paths:
            detail=read_json(path)
            before=len(detail['events'])
            compact_detail(detail,cap=cap)
            if len(detail['events'])<before: detail['truncation']['budget_limited']=True
            write_json(path,detail)
        if size()<budget-100_000: break
    if size()>=budget-100_000:
        raise ValueError('Checkpoint/issuer/monthly metadata exceed site byte budget; previous generation retained')
    meta=read_json(stage/'meta.json')
    missing_usd,missing_class,retained,omitted=0,0,0,0
    for path in paths:
        detail=read_json(path)
        transfers=[e for e in detail['events'] if e['kind'] in ('in','out')]
        missing_usd+=sum(e.get('usd') is None for e in transfers)
        missing_class+=sum(e.get('class') not in ('real','dust','poisoning') for e in transfers)
        retained+=len(transfers)
        omitted+=detail['truncation']['omitted_transfer_events']
    meta.setdefault('missing',{}).update({'address.events.usd':missing_usd,'address.events.class':missing_class})
    meta['export_counts'].update(files=len(list(stage.rglob('*.json'))),
        bytes_before_meta=size()-(stage/'meta.json').stat().st_size,
        retained_transfer_events=retained,omitted_transfer_events=omitted)
    meta['event_retention']='Display samples bounded by 2,000 transfers and 1.5 MB per address, further sampled for the 100 MB export budget. All issuer/designation/delisting events stay. Full saved-history monthly counts include omitted window and other transfers; truncation records their counts. Full row evidence stays in saved timelines.'
    meta['size_limits']={'total_json_bytes':budget,'per_address_json_bytes':1_500_000}
    write_json(stage/'meta.json',meta)
    if size()>budget or any(p.stat().st_size>1_500_000 for p in paths): raise ValueError('Final export byte limits exceeded')
    return size()

def _export(root=ROOT, refreshed=None, source_status=None, check=False, input_snapshot=None):
    root = Path(root)
    target = root/'site/data'
    target.mkdir(parents=True,exist_ok=True)
    with (target/'.export.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix='las-site-export-',dir='/tmp') as temp:
            stage = Path(temp)
            exporter=Exporter(root,stage,refreshed,source_status,input_snapshot)
            try: summary=exporter.run()
            finally: exporter.inflow_index.close()
            metadata=read_json(stage/'meta.json')
            metadata['input_snapshot']=published_inputs.public_info(input_snapshot)
            write_json(stage/'meta.json',metadata)
            summary['bytes'] = fit_budget(stage)
            summary['missing_fields']=read_json(stage/'meta.json')['missing']
            if check:
                compare_exports(target, stage)
            else:
                # Atomic per file, meta last. Failed generation construction never changes the site.
                files = sorted(stage.rglob('*.json'),key=lambda p:(p.name=='meta.json',str(p)))
                expected_paths = {p.relative_to(stage) for p in files}
                for p in files:
                    dest = target/p.relative_to(stage)
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    atomic_copy(p,dest)
                for p in (target/'address').glob('*/*.json'):
                    if p.relative_to(target) not in expected_paths: p.unlink()
            return summary

def export(root=ROOT, refreshed=None, source_status=None, check=False, input_snapshot=None):
    if Path(root)==ROOT:
        snapshot=published_inputs.current()
        if snapshot:
            with Generation() as gen:
                gen.snapshot('data/timelines',ROOT/snapshot['path']/'timelines')
                return _export(gen.root,refreshed,source_status,check,snapshot)
    return _export(root,refreshed,source_status,check,input_snapshot)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--refreshed-at',help='UTC completion time supplied only by refresh')
    args = parser.parse_args()
    result = export(refreshed=args.refreshed_at,check=args.check)
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
