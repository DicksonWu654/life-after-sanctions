"""Offline joins and compact presentation views of saved analysis outputs."""
from collections import Counter, defaultdict
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from zoneinfo import ZoneInfo

from .pipeline_io import read_json, json_bytes


def quantity(value, unit, valued_at=None):
    out = {'value':value, 'unit':unit}
    if valued_at is not None: out['valued_at'] = valued_at
    return out


def csv_rows(path):
    csv.field_size_limit(100_000_000)
    if not path.exists(): return
    with path.open(newline='') as stream:
        yield from csv.DictReader(stream)


def decimal_text(value):
    try: return str(Decimal(str(value)).normalize())
    except InvalidOperation: return str(value)


def event_identity(event, index):
    return event.get('event_id') or f"{event.get('hash')}:{event.get('kind',event.get('event_type','event'))}:{event.get('logIndex',event.get('traceId',index))}:{event.get('transfer_ordinal',0)}"


class InflowIndex:
    """Disk-backed classification join; only one address is resident at a time."""
    FIELDS = ('chain','address','event_id','hash','asset','amount','time_utc','inflow_class',
              'classification_rule','classification_confidence','usd','valued_at','price_raw_ref')

    def __init__(self, root):
        self.temp = self.db = None
        path = root/'data/derived/inflows.csv'
        if not path.exists(): return
        self.temp = tempfile.TemporaryDirectory(prefix='las-inflow-index-',dir='/tmp')
        self.db = sqlite3.connect(str(Path(self.temp.name)/'events.sqlite'))
        self.db.execute('PRAGMA journal_mode=OFF')
        self.db.execute('PRAGMA synchronous=OFF')
        self.db.execute('CREATE TABLE events ('+','.join(f'"{f}" TEXT' for f in self.FIELDS)+')')
        self.db.executemany('INSERT INTO events VALUES ('+','.join('?' for _ in self.FIELDS)+')',
                            (tuple(r.get(f,'') for f in self.FIELDS) for r in csv_rows(path)))
        self.db.execute('CREATE INDEX address_events ON events(chain,address)')
        self.db.commit()

    def address(self, chain, address):
        exact, semantic = defaultdict(list), defaultdict(list)
        if self.db:
            for values in self.db.execute('SELECT * FROM events WHERE chain=? AND address=?',(chain.upper(),address)):
                r = dict(zip(self.FIELDS,values))
                exact[r['event_id']].append(r)
                semantic[(r['hash'],r['asset'],decimal_text(r['amount']),r['time_utc'])].append(r)
        return exact, semantic

    @staticmethod
    def match(indexes, event, index):
        exact, semantic = indexes
        identity = event_identity(event,index)
        signature=(event.get('hash'),event.get('asset'),decimal_text(event.get('amount')),event.get('time_utc'))
        candidates=[r for r in exact.get(identity,[]) if (r['hash'],r['asset'],decimal_text(r['amount']),r['time_utc'])==signature]
        candidates=candidates or semantic.get(signature,[])
        # Repeated equal logs may have the same classification, but selecting
        # one arbitrary raw event would manufacture an exact event-level join.
        if len(candidates) == 1: return candidates[0]
        return None

    def close(self):
        if self.db: self.db.close()
        if self.temp: self.temp.cleanup()


def valuation_fields(obj):
    """Keep the original valuation statement and add an honest structured basis."""
    if isinstance(obj,list):
        for value in obj: valuation_fields(value)
    elif isinstance(obj,dict):
        if str(obj.get('unit','')).startswith('usd'):
            at = obj.get('valued_at')
            if isinstance(at,str) and re.fullmatch(r'\d{4}-\d\d-\d\d(?:T[^ ]+)?',at):
                obj['valued_at_iso'] = at
                obj['valuation_basis'] = 'stated_timestamp'
            else:
                text = str(at).lower()
                basis = ('at_each_transfer_time' if 'transfer' in text or 'outgoing' in text else
                         'at_each_freeze_time' if 'blacklist' in text or 'freeze' in text else
                         'mixed_designation_dates' if 'designation' in text or 'own t' in text else
                         'latest_saved_observations' if 'latest' in text or 'fetched' in text else
                         'mixed_daily_prices' if 'day' in text else 'unspecified')
                obj['valued_at_iso'] = None
                obj['valuation_basis'] = basis
        for value in list(obj.values()):
            if isinstance(value,(dict,list)): valuation_fields(value)
    return obj


def enrich_headlines(headlines, results):
    by_id = {r['id']:r for r in headlines}
    p = results.get('premove',{})
    for candidate in p.get('candidate_findings',[]):
        if candidate.get('id') == 'population_pre_week' and candidate['id'] in by_id:
            card = by_id[candidate['id']]
            for field in ('observed_share','baseline_share','denominator','number','p_holm'):
                card[field] = candidate.get(field)
            card['big'] = candidate['observed_share']
            card['sentence'] = (f"{candidate['observed_share']['value']:.2%} active in the pre-listing week versus "
                                f"{candidate['baseline_share']['value']:.2%} in their own baseline weeks.")
            card['basis'] = 'Equal-address descriptive shares among the preregistered eligible non-Tornado cohort; not evidence of advance notice.'
    inflows = results.get('inflows',{})
    wallet = inflows.get('wallet_during_sanctions',{})
    share = inflows.get('classification_audit',{}).get('dust_or_operational_spam_share_of_incoming_records')
    if share and wallet:
        n = wallet['dust_events']['value'] + wallet['poisoning_events']['value']
        common = {'finding_ref':'results/inflows.json','raw_ref':'data/derived/inflows.csv',
                  'source_url':'results/inflows.json','detail_md':'Saved recognized-asset/value and operational-spam filters; not a count of people or proof of sender intent.'}
        additions = [dict(common,id='inflows_dust_share',big=share,
            sentence=f"Dust or operational spam accounted for {share['value']:.2%} of {wallet['inflow_events']['value']:,} incoming transfer records to non-Tornado listed addresses during listing periods.",
            numerator=quantity(n,'events'),denominator=wallet['inflow_events'],
            basis='Incoming transfer records during listing periods; one unpriced unresolved record remains outside these classified buckets.'),
            dict(common,id='inflows_real_events',big=wallet['real_events'],usd=wallet['real_inflow_usd'],
            receiving_addresses=wallet['receiving_addresses'],denominator=wallet['inflow_events'],
            sentence=f"{wallet['real_events']['value']:,} incoming transfers passed the study's value and token filters during listing periods.",
            basis='Observed incoming asset-transfer events, not transactions or people; USD valued at each transfer.')]
        for card in additions:
            if card['id'] in by_id: by_id[card['id']].update(card)
            else: headlines.append(card)
    for candidate in results.get('tornado',{}).get('findings',[]):
        card = by_id.get(candidate.get('id'))
        if not card or 'before' not in candidate or 'after' not in candidate: continue
        card.update(before=candidate['before'],after=candidate['after'],window_days=30)
        event_id = candidate['id'].removeprefix('tornado_')
        event = next((e for e in results['tornado'].get('legal_events',[]) if e['id']==event_id),{})
        card['event_date'] = event.get('date')
        card['basis'] = 'Equal 30-day UTC windows excluding event date; descriptive native ETH deposits.'
    for card in headlines:
        if card['big'].get('unit') == 'share' and not card.get('basis'):
            card['basis'] = card.get('sentence','')
        valuation_fields(card)
        if 'valuation_basis' in card['big']:
            card['valuation_basis'] = card['big']['valuation_basis']
            card['valued_at_iso'] = card['big']['valued_at_iso']
    return headlines


def sankey_cohorts(root, graph, entity_names, flows):
    """Reproduce the producer's Decimal allocation and split every link by UID set."""
    if flows.get('summary',{}).get('wallet_outflows_usd',{}).get('value') is None:
        graph['cohort_split_missing'] = 'No saved results/flows.json total to reconcile against'
        return graph
    allocations = {view:defaultdict(lambda:defaultdict(Decimal)) for view in ('program','chain')}
    totals = defaultdict(Decimal)
    for r in csv_rows(root/'data/derived/flows_edges.csv'):
        if r['included_in_total']!='True' or not r['usd'] or r['is_dust']=='True' or r['tornado_contract']=='True' or r['self_transfer_same_address']=='True': continue
        amount = Decimal(r['usd'])
        uids = tuple(sorted(filter(None,r['source_entity_uids'].split(';'))))
        cls = {'cex_hot':'cex_deposit','issuer':'unlabelled','defi_other':'unlabelled'}.get(r['destination_class'],r['destination_class'])
        programs = sorted(set(filter(None,r['programs'].split(';')))) or ['UNSPECIFIED']
        totals['all'] += amount
        if cls=='unlabelled': totals['unlabelled'] += amount
        if '55505' not in uids:
            totals['excluding'] += amount
            if cls=='unlabelled': totals['excluding_unlabelled'] += amount
        for view, sources in (('chain',[r['chain']]),('program',programs)):
            for source in sources: allocations[view][(f'{view}:{source}',f'class:{cls}')][uids] += amount/len(sources)
    if not totals['all']:
        graph['cohort_split_missing'] = 'No eligible saved flows_edges.csv rows'
        return graph
    target = Decimal(str(flows['summary']['wallet_outflows_usd']['value']))
    if abs(target-totals['all']) > Decimal('.02'): raise ValueError('Sankey edge cohort does not reconcile to results/flows.json')
    links, excluding = [], []
    for view in ('program','chain'):
        for original in flows.get('sankey',{}).get(view,{}).get('links',[]):
            groups = allocations[view][(original['source'],original['target'])]
            if abs(sum(groups.values())-Decimal(str(original['value']))) > Decimal('.000002'):
                raise ValueError('Sankey link mismatch: '+str(original))
            cohorts=[]
            for uids,value in sorted(groups.items()):
                names = sorted({n for uid in uids for n in entity_names.get(uid,())})
                cohorts.append({'cohort':'; '.join(names) or 'Unresolved OFAC UID set','sdn_uids':list(uids),
                                'sdn_uid':uids[0] if len(uids)==1 else None,'value':round(float(value),6)})
            links.append(dict(original,by_cohort=cohorts))
            remaining = sum(v for uids,v in groups.items() if '55505' not in uids)
            if remaining: excluding.append(dict(source=original['source'],target=original['target'],value=round(float(remaining),6)))
    graph.update(links=links,links_excluding={'CHEN, Zhi':excluding},
        unlabelled_share=quantity(float(totals['unlabelled']/totals['all']),'share'),
        unlabelled_share_excluding={'CHEN, Zhi':quantity(float(totals['excluding_unlabelled']/totals['excluding']) if totals['excluding'] else None,'share')},
        total_usd=quantity(float(totals['all']),'usd','at each transfer time'),
        total_usd_excluding={'CHEN, Zhi':quantity(float(totals['excluding']),'usd','at each transfer time')},
        cohort_rule='Disjoint source OFAC UID sets; a multi-UID edge is counted once. Excluding CHEN, Zhi removes every edge whose saved source_entity_uids contains 55505. Program tags split each edge equally; program and chain are alternative views.',
        cohort_split_source={'source_url':'results/flows.json','raw_ref':'data/derived/flows_edges.csv'})
    return graph


def slim_amount(value):
    if not isinstance(value,dict): return value
    return valuation_fields({k:value[k] for k in ('value','unit','valued_at','valued_at_iso','valuation_basis') if k in value})


def slim_freezes(points):
    out=[]
    for point in points:
        row={k:v for k,v in point.items() if k not in ('raw_ref','amount_frozen')}
        row['amount_frozen']=slim_amount(point.get('amount_frozen'))
        row['evidence_ref']='freezes_evidence.json#'+':'.join((point['issuer'],point['chain'],point['address']))
        out.append(row)
    return out


def extra_cases(index, matched, checkpoints, freeze_result):
    cases=[]
    for uid,case_id in (('4632','bank-markazi-iran'),('58361','xinbi-guarantee')):
        members=[r for r in index if any(e['uid']==uid for e in r['entities'])]
        if not members: continue
        ids={r['id'] for r in members}
        rows=[r for r in matched if r['listing_relation']=='OFAC-listed chain' and r['chain'].lower()+':'+r['address'] in ids]
        names=sorted({e['name'] for r in members for e in r['entities'] if e['uid']==uid})
        urls=sorted({url for r in rows for url in json.loads(r['source_url'])})
        events=[]
        for member in members:
            events.append({'date':member['listed'],'kind':'designation','label':'OFAC published this address',
                           'address_id':member['id'],'source_url':next((u for u in urls if member['listed'].replace('-','') in u),urls[0] if urls else member['source_url'])})
        for r in rows:
            pub=dt.datetime.fromisoformat(r['T_pub_utc'].replace('Z','+00:00'))
            for source in json.loads(r['issuer_events']):
                kind='freeze' if source['event'] in ('AddedBlackList','Blacklisted') else 'burn' if 'Destroyed' in source['event'] else 'unfreeze'
                at=dt.datetime.fromisoformat(source['timestamp'].replace('Z','+00:00'))
                event={'date':source['timestamp'],'kind':kind,'label':source['event'],
                    'address_id':r['chain'].lower()+':'+r['address'], 'asset':r['token'],
                    'lag_hours':(at-pub).total_seconds()/3600,
                    'lag_hours_interval':[(at-dt.datetime.fromisoformat(r['T_pub_latest_utc'].replace('Z','+00:00'))).total_seconds()/3600,
                                          (at-dt.datetime.fromisoformat(r['T_pub_earliest_utc'].replace('Z','+00:00'))).total_seconds()/3600],
                    'tx':{'chain':r['chain'].lower(),'hash':source['tx_hash'],'explorer_url':source['source_url']},
                    'source_url':source['source_url'],'raw_ref':source['raw_ref']}
                if source['timestamp']==r['first_blacklist_utc']:
                    event['amount']=slim_amount(json.loads(r['freeze_balance_usd'])) if r.get('freeze_balance_usd') else None
                    event['amount_native']=quantity(float(r['balance_at_first_freeze_native']) if r.get('balance_at_first_freeze_native') else None,'native:'+r['token'])
                events.append(event)
        balances=[r['balance_today_usd'] for r in members if r['balance_today_usd'] is not None]
        times=sorted({str(v['valued_at']) for v in balances})
        total=quantity(sum(v['value'] for v in balances),'usd','each address latest saved observation') if balances else None
        if total: total.update(valuation_times=times,partial=len(balances)!=len(members),valuation_basis='latest_saved_observations',valued_at_iso=times[0] if len(times)==1 else None)
        findings=[f for f in freeze_result.get('findings',[]) if uid=='4632' and f.get('id')=='iran-two-prelisting-freezes']
        cases.append({'id':case_id,'name':'; '.join(names),'program':'; '.join(sorted({p for r in members for p in r['programs']})),
            'designated':min(r['listed'] for r in members),'press_release_url':urls[0] if urls else None,
            'chains':sorted({r['chain'] for r in members}), 'addresses':sorted(ids),
            'one_liner':'Saved issuer events place each freeze against the publication date of its exact OFAC-listed identifier.',
            'events':sorted(events,key=lambda e:(e['date'],e.get('address_id',''),e['kind'])),
            'today':{'balance_usd':total,'status_sentence':'Latest saved observations; blacklist membership does not freeze native TRX.',
                     'covers':f"{len(balances)} of {len(members)} listed chain-address pairs with known recognized-asset balances."},
            'findings':findings,'source_url':urls,'raw_ref':['results/freeze_match.json','data/derived/freeze_match.csv','data/derived/address_summary.csv'],
            'provisional':freeze_result.get('provisional',True),'scope':{'addresses':quantity(len(members),'addresses')},'issuer_events':events})
    return cases


def compact_case(case):
    row={k:v for k,v in case.items() if k not in ('issuer_events','address_metrics')}
    row['evidence_ref']='cases_evidence.json#'+case['id']
    def strip(obj):
        if isinstance(obj,list): return [strip(v) for v in obj]
        if not isinstance(obj,dict): return obj
        return {k:strip(v) for k,v in obj.items() if k not in ('price_evidence','counterparty_candidates','price_raw_ref')}
    return valuation_fields(strip(row))


def compact_detail(detail, cap=2000, byte_limit=1_500_000):
    """Bound the display sample; retain full-history monthly counts separately."""
    events=detail['events']
    fixed=[e for e in events if e['kind'] not in ('in','out')]
    transfers=[e for e in events if e['kind'] in ('in','out')]
    windows=detail['truncation'].get('designation_window_dates',[])
    dates=[dt.datetime.fromisoformat(d[:10]).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(dt.timezone.utc) for d in windows]
    keys=set(detail.pop('_key_transfer_hashes',[]))
    for event in transfers:
        if event.get('tx') in keys: event['key_event']=True
    # Selection is deterministic; evidence remains in the full saved timeline.
    def in_window(e):
        time=dt.datetime.fromisoformat(e['time'].replace('Z','+00:00'))
        return any(d-dt.timedelta(days=7)<=time<=d+dt.timedelta(days=7) for d in dates)
    def select(n):
        newest=sorted(transfers,key=lambda e:(e['time'],str(e.get('tx',''))),reverse=True)[:n//2]
        ids={id(e) for e in newest}
        ranked=sorted((e for e in transfers if id(e) not in ids),
            key=lambda e:(bool(e.get('key_event')), bool(in_window(e) and (e.get('usd') or 0)>=1),
                          (e.get('usd') or 0)>=1, e.get('usd') or 0, in_window(e),e['time'],str(e.get('tx',''))),reverse=True)
        return sorted(fixed+newest+ranked[:max(0,n-len(newest))],key=lambda e:e.get('time') or '',reverse=True)
    tr=detail['truncation']
    observed_windows=tr.get('observed_designation_window_transfers',sum(in_window(e) for e in transfers))
    limit=min(cap,len(transfers))
    while True:
        detail['events']=select(limit)
        retained=[e for e in detail['events'] if e['kind'] in ('in','out')]
        window_kept=sum(in_window(e) for e in retained)
        tr.update(truncated=tr['observed_transfer_events']>len(retained),
            retained_transfer_events=len(retained),omitted_transfer_events=tr['observed_transfer_events']-len(retained),
            newest_limit=limit,display_transfer_limit=limit,
            retained_designation_window_transfers=window_kept,
            omitted_designation_window_transfers=max(0,observed_windows-window_kept),
            per_file_byte_limit=byte_limit,
            rule='Display sample: half newest transfers, then key checkpoint examples and largest priced non-dust transfers, prioritizing designation-window events. All designation/delisting/issuer events retained. Window transfers can be sampled for byte/count limits. Full monthly counts and source timelines cover omitted transfers.')
        if len(json_bytes(detail))<=byte_limit: break
        if not limit:
            raise ValueError('Checkpoint/issuer metadata alone exceeds the per-address byte limit: '+detail['id'])
        limit=int(limit*.7)
        tr['budget_limited']=True
    return detail
