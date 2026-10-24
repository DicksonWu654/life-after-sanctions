#!/usr/bin/env python3
"""Rebuild OFAC evidence ledger offline; --fetch refreshes public inputs.

All dependencies are Python standard-library modules. No upstream code is run.
CSV cells containing lists use semicolons; feature_records/listing_events are JSON.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import difflib
import hashlib
import io
import json
from pathlib import Path
import random
import re
import sys
import unicodedata

from chains import assign, EXPLORERS
from parse import action_html, advanced_xml, patch_changes, simple_xml
from sources import ROOT, RAW, atomic, fetch, index, read_entry

OFFICIAL = {
    'sdn_advanced': 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML',
    'sdn': 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML',
    'consolidated_advanced': 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/CONS_ADVANCED.XML',
}
HISTORICAL = {
    'historic_sdn_202208': 'https://web.archive.org/web/20220808155600id_/https://www.treasury.gov/ofac/downloads/sdn.xml',
    'historic_sdn_2023': 'https://web.archive.org/web/20230623105856id_/https://www.treasury.gov/ofac/downloads/sdn.xml',
    'treasury_tornado_delisting': 'https://home.treasury.gov/news/press-releases/sb0057',
    'b10c_readme': 'https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/main/README.md',
}

def normalized(address):
    a = address.strip()
    if re.fullmatch('41[0-9a-fA-F]{40}',a):
        return assign('TRX',a)['address_normalized']
    return a.lower() if a.lower().startswith(('0x', 'bc1', 'ltc1')) else a

def namekey(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name).upper() if c.isalnum())

def joined(values):
    return ';'.join(sorted(set(v for v in values if v)))

def dumps(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def csv_bytes(rows, fields=None):
    fields = fields or list(rows[0])
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fields, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()

def all_actions(manifest):
    actions = []
    for key, meta in sorted(manifest.items()):
        if key.startswith('action_'):
            date = key[7:11] + '-' + key[11:13] + '-' + key[13:15]
            actions.append(action_html(read_entry(meta), date, meta['url'], meta['raw_ref']))
    return actions

def derive():
    manifest = index()
    current = simple_xml(read_entry(manifest['sdn']))
    features, types, issue = advanced_xml(read_entry(manifest['sdn_advanced']))
    consolidated, cons_types, cons_issue = advanced_xml(read_entry(manifest['consolidated_advanced']))
    if consolidated:
        raise ValueError('Consolidated list now has digital-currency features; add its identity parser before publishing')
    # Independent official schemas must agree down to UID, ticker, and source text.
    advanced_set = Counter((f['sdn_uid'], f['ticker'], f['address']) for f in features)
    simple_set = Counter((uid,t,a) for uid,e in current.items() for t,a,_ in e['ids'])
    if advanced_set != simple_set:
        raise ValueError(f'Official XML formats disagree: {advanced_set-simple_set}; {simple_set-advanced_set}')
    identities = {uid: e for uid,e in current.items() if e['ids']}
    historic = []
    # Archived OFAC bytes provide historical UIDs, not guessed entity identities.
    snapshots = {v['raw_ref']:v for k,v in manifest.items() if k.startswith('historic_sdn_')}
    fetch_log = RAW/'fetches.jsonl'
    if fetch_log.exists():
        for line in fetch_log.read_text().splitlines():
            v = json.loads(line)
            if v['key']=='sdn' and v['raw_ref']!=manifest['sdn']['raw_ref']:
                snapshots.setdefault(v['raw_ref'],v)
    for meta in snapshots.values():
        for uid,e in simple_xml(read_entry(meta)).items():
            if not e['ids']:
                continue
            identities.setdefault(uid,e)
            for t,a,i in e['ids']:
                historic.append(dict(sdn_uid=uid, ticker=t, address=a, feature_id='',
                    historical_id=i, raw_ref=meta['raw_ref'], source_url=meta['url']))
    aliases = defaultdict(set)
    alias_strings = []
    for uid,e in identities.items():
        for name in [e['sdn_name']] + e.get('aliases',[]):
            aliases[namekey(name)].add(uid)
            alias_strings.append((name.upper(),uid))
    alias_strings.sort(key=lambda v: (-len(v[0]),v))
    tornado = {uid for uid,e in identities.items() if e['sdn_name'] == 'TORNADO CASH'}

    def identify(m):
        if m['entity'].startswith('TORNADO CASH') and tornado:
            # OFAC withdrew the first entry and created the replacement on Nov 8.
            old = '38499'
            if m['date'] < '2022-11-08' or (m['date'] == '2022-11-08' and m['section']=='deletion'):
                return old
            newer = sorted(tornado - {old})
            if len(newer) == 1:
                return newer[0]
        matches = aliases.get(namekey(m['entity']), set())
        if len(matches) == 1:
            return next(iter(matches))
        # OFAC sometimes puts the first geographic address after a comma.
        upper = m['entity'].upper()
        for alias,uid in alias_strings:
            if upper.startswith(alias + ','):
                return uid
        return 'unknown:' + hashlib.sha256(namekey(m['entity']).encode()).hexdigest()[:16]

    groups = {}
    def group(address, uid):
        key = (normalized(address),uid)
        return groups.setdefault(key, dict(current=[], historic=[], mentions=[]))
    for f in features:
        group(f['address'],f['sdn_uid'])['current'].append(f)
    for f in historic:
        group(f['address'],f['sdn_uid'])['historic'].append(f)
    actions = all_actions(manifest)
    page_events = []
    for action in actions:
        for m in action['mentions']:
            m['sdn_uid'] = identify(m)
            group(m['address'],m['sdn_uid'])['mentions'].append(m)
        # Compare old/new text within each page, per entity; alias repeats collapse.
        before = defaultdict(set)
        after = defaultdict(set)
        for m in action['mentions']:
            key = m['sdn_uid']
            addr = normalized(m['address'])
            if m['section']=='update_before':
                before[key].add(addr)
            elif m['section']=='update_after':
                after[key].add(addr)
        for m in action['mentions']:
            addr = normalized(m['address'])
            kind = ''
            if m['section']=='addition':
                kind = 'addition'
            elif m['section']=='deletion':
                kind = 'removal'
            elif m['section']=='update_after' and addr not in before[m['sdn_uid']]:
                kind = 'addition'
            elif m['section']=='update_before' and addr not in after[m['sdn_uid']]:
                kind = 'removal'
            if kind:
                page_events.append(dict(date=m['date'],kind=kind,sdn_uid=m['sdn_uid'],
                    address=addr,url=m['url'],title=m['title'],raw_ref=m['raw_ref'],
                    programs=m['programs'],entity=m['entity']))
    event_map = defaultdict(list)
    unique_events = {}
    for ev in page_events:
        unique_events[(ev['date'],ev['kind'],ev['sdn_uid'],ev['address'],ev['url'])] = ev
    page_events = sorted(unique_events.values(),key=lambda e:(e['date'],e['kind'],e['sdn_uid'],e['address']))
    for ev in page_events:
        event_map[(ev['address'],ev['sdn_uid'])].append(ev)

    ledger = []
    for (addr,uid),g in sorted(groups.items()):
        fs = g['current'] or list({(f['ticker'],f['address'],f.get('historical_id','')):f for f in g['historic']}.values())
        mentions = sorted(g['mentions'],key=lambda m:(m['date'],m['url'],m['ticker']))
        # Historical pages may contain alias repetitions; retain only one entity link.
        if not fs:
            seen = set()
            for m in mentions:
                if m['ticker'] not in seen:
                    fs.append(dict(address=m['address'],ticker=m['ticker'],feature_id='',sdn_uid=uid,
                                   raw_ref=m['raw_ref'],source_url=m['url']))
                    seen.add(m['ticker'])
        if not fs:
            continue
        fs = sorted(fs,key=lambda f:(f['ticker'] in ('USDT','USDC'), f['ticker']!='ETH',f['ticker'],f['address']))
        first = fs[0]
        details = assign(first['ticker'],first['address'])
        all_features = []
        for f in fs:
            d = assign(f['ticker'],f['address'])
            all_features.append(dict(ticker=f['ticker'],chain=d['chain'],feature_id=f['feature_id'],address=f['address'],
                                     historical_id=f.get('historical_id','')))
        e = identities.get(uid)
        entity_name = e['sdn_name'] if e else (mentions[0]['entity'] if mentions else '')
        programs = e['programs'] if e else joined(p for m in mentions for p in m['programs'].split(';'))
        evs = event_map.get((addr,uid),[])
        adds = [ev for ev in evs if ev['kind']=='addition']
        removals = [ev for ev in evs if ev['kind']=='removal']
        listed = adds[0] if adds else None
        # The replacement Tornado UID inherits first-publication dates from UID 38499.
        record_date = listed['date'] if listed else ''
        if entity_name == 'TORNADO CASH' and uid != '38499':
            previous = [ev for ev in event_map.get((addr,'38499'),[]) if ev['kind']=='addition']
            if previous and (listed is None or previous[0]['date'] < listed['date']):
                listed = previous[0]
        current_flag = bool(g['current'])
        removed = removals[-1] if removals and not current_flag else None
        reason = ''
        if listed:
            if mentions and mentions[0]['date'] < listed['date']:
                # Seeing an address in a pre-change record proves an earlier listing.
                reason = 'An earlier before-state mentions the address; original publication not established'
                listed = None
        if not listed:
            reason = reason or 'No explicit addition or before/after address addition found in archived OFAC pages'
        raw_ref = manifest['sdn_advanced']['raw_ref'] if current_flag else (fs[0].get('raw_ref') or (mentions[0]['raw_ref'] if mentions else ''))
        source_url = OFFICIAL['sdn_advanced'] if current_flag else (fs[0].get('source_url') or (mentions[0]['url'] if mentions else ''))
        source_ids = joined('sdn_advanced.xml#Feature/'+f['feature_id'] for f in g['current'])
        row = dict(address=first['address'],address_normalized=details.pop('address_normalized'),
            ticker=first['ticker'],chain=details.pop('chain'),sdn_uid='' if uid.startswith('unknown:') else uid,
            sdn_name=entity_name,sdn_type=e['sdn_type'] if e else ('individual' if any('(individual)' in m['text'] for m in mentions) else 'entity'),
            programs=programs,listed_date=listed['date'] if listed else '',
            listed_action_url=listed['url'] if listed else '',listed_action_title=listed['title'] if listed else '',
            delisted_date=removed['date'] if removed else '',delisted_action_url=removed['url'] if removed else '',
            trackable=details.pop('trackable'),untrackable_reason=details.pop('untrackable_reason'),source=source_ids or 'historical_ofac_entry',
            tickers=joined(f['ticker'] for f in fs),chains=joined(f['chain'] for f in all_features),
            entity_key=uid,current_in_sdn=str(current_flag).lower(),
            status='current' if current_flag else ('delisted' if removed else 'historical_missing_current'),
            listed_date_method='recent_actions_page' if listed else 'unknown',
            listed_date_confidence='high' if listed else 'unknown',listed_date_reason=reason,
            listed_raw_ref=listed['raw_ref'] if listed else '',entity_record_listed_date=record_date,
            delisted_date_method='recent_actions_page' if removed else ('not_applicable' if current_flag else 'unknown'),
            delisted_date_confidence='high' if removed else '',delisted_raw_ref=removed['raw_ref'] if removed else '',
            sdn_uid_reason='Not recovered from an archived OFAC XML; entity_key is an internal key' if uid.startswith('unknown:') else '',
            raw_ref=raw_ref,source_url=source_url,**details,
            feature_count=len(g['current']),feature_records=dumps(all_features),
            listing_events=dumps([{k:ev[k] for k in ('date','kind','url','raw_ref')} for ev in evs]))
        ledger.append(row)

    ledger.sort(key=lambda r:(r['chain'],r['address_normalized'],r['entity_key']))
    addresses_map = defaultdict(list)
    for row in ledger:
        for chain in row['chains'].split(';'):
            addresses_map[(chain,row['address_normalized'])].append(row)
    addresses = []
    for (chain,addr),rows in sorted(addresses_map.items()):
        dates = sorted(r['listed_date'] for r in rows if r['listed_date'])
        active = any(r['current_in_sdn']=='true' for r in rows)
        addresses.append(dict(address=rows[0]['address'],address_normalized=addr,chain=chain,
            first_listed_date=dates[0] if dates else '',all_entity_uids=joined(r['sdn_uid'] for r in rows),
            sdn_uids=joined(r['sdn_uid'] for r in rows),programs=joined(p for r in rows for p in r['programs'].split(';')),
            trackable=str(any(r['trackable']=='true' for r in rows)).lower(),
            untrackable_reason=joined(r['untrackable_reason'] for r in rows if r['trackable']=='false'),
            tickers=joined(f['ticker'] for r in rows for f in json.loads(r['feature_records']) if f['chain']==chain),
            current_in_sdn=str(active).lower(),delisted_date='' if active else max((r['delisted_date'] for r in rows),default=''),
            tron_hex=rows[0]['tron_hex'],explorer_url=EXPLORERS.get(chain,''),
            source_url=joined(r['source_url'] for r in rows),raw_ref=joined(r['raw_ref'] for r in rows)))

    actions_map = defaultdict(list)
    for a in actions:
        if a['mentions']:
            actions_map[a['date']].append(a)
    actions_out = []
    for date, pages in sorted(actions_map.items()):
        events = [e for e in page_events if e['date']==date]
        added = {e['address'] for e in events if e['kind']=='addition'}
        removed = {e['address'] for e in events if e['kind']=='removal'}
        actions_out.append(dict(date=date,url=joined(p['url'] for p in pages),title=joined(p['title'] for p in pages),
            programs=joined(x for p in pages for m in p['mentions'] for x in m['programs'].split(';')),
            n_addresses_added=len(added),n_addresses_removed=len(removed),
            entities_named=joined(identities[m['sdn_uid']]['sdn_name'] if m['sdn_uid'] in identities else m['entity'] for p in pages for m in p['mentions']),
            n_entities=len({m['sdn_uid'] for p in pages for m in p['mentions']}),
            n_addresses_mentioned=len({normalized(m['address']) for p in pages for m in p['mentions']}),
            n_addresses_added_and_removed=len(added & removed),
            raw_ref=joined(p['mentions'][0]['raw_ref'] for p in pages),source_url=joined(p['url'] for p in pages)))

    # Current cross-check is exact by raw ticker and canonical address.
    ofac = {(f['ticker'],normalized(f['address'])) for f in features}
    b10c = set()
    current_tickers = {o['path'].removeprefix('sanctioned_addresses_').removesuffix('.json')
                       for o in json.loads(read_entry(manifest['b10c_tree']))['tree']
                       if o['path'].startswith('sanctioned_addresses_') and o['path'].endswith('.json')}
    for key,meta in manifest.items():
        if key.startswith('b10c_current_') and key[len('b10c_current_'):] in current_tickers:
            ticker = key[len('b10c_current_'):]
            b10c.update((ticker,normalized(a)) for a in json.loads(read_entry(meta)))
    history = []
    for key in sorted(k for k in manifest if k.startswith('b10c_commits_')):
        history.extend(json.loads(read_entry(manifest[key])))
    history_removals = []
    for c in reversed(history):
        added,removed = patch_changes(read_entry(manifest['b10c_patch_'+c['sha']]))
        canon_added = {(t,normalized(a)) for t,a in added}
        for t,a in removed:
            history_removals.append(dict(date=c['commit']['author']['date'][:10],ticker=t,address=a,
                kind='case_only' if (t,normalized(a)) in canon_added else 'removed',
                url='https://github.com/0xB10C/ofac-sanctioned-digital-currency-addresses/commit/'+c['sha'],
                raw_ref=manifest['b10c_patch_'+c['sha']]['raw_ref']))
    missing_history_removals = [h for h in history_removals if h['kind']!='case_only' and not any(
        r['address_normalized']==normalized(h['address']) and r['delisted_date'] for r in ledger)]
    if missing_history_removals:
        raise ValueError(f'Unreconciled GitHub history removals: {missing_history_removals}')
    ofac_tickers, b10c_tickers = defaultdict(set), defaultdict(set)
    for t,a in ofac:
        ofac_tickers[a].add(t)
    for t,a in b10c:
        b10c_tickers[a].add(t)
    ticker_differences = [(a,sorted(ofac_tickers[a]),sorted(b10c_tickers[a]))
                         for a in sorted(ofac_tickers.keys() & b10c_tickers.keys())
                         if ofac_tickers[a] != b10c_tickers[a]]
    report = dict(issue=issue,consolidated_issue=cons_issue,types=types,
        feature_count=len(features),distinct_source_addresses=len({normalized(f['address']) for f in features}),
        current_pairs=len({(normalized(f['address']),f['sdn_uid']) for f in features}),
        current_entities=len({f['sdn_uid'] for f in features}),by_ticker=Counter(f['ticker'] for f in features),
        by_program={p:len({normalized(f['address']) for f in features if p in current[f['sdn_uid']]['programs'].split(';')})
                    for p in sorted({p for f in features for p in current[f['sdn_uid']]['programs'].split(';')})},
        ofac_not_b10c=sorted(ofac-b10c),b10c_not_ofac=sorted(b10c-ofac),
        ticker_differences=ticker_differences,
        history_removals=history_removals,actions_scanned=len(actions),consolidated_count=len(consolidated),
        b10c_commits=len(history),unknown_uid_rows=sum(not r['sdn_uid'] for r in ledger))
    # Explicit invariants make --check fail on lost rows or features.
    assert sum(r['feature_count'] for r in ledger)==len(features)
    assert sum(r['current_in_sdn']=='true' for r in ledger)==report['current_pairs']
    assert len({r['address_normalized'] for r in ledger if r['current_in_sdn']=='true'})==report['distinct_source_addresses']
    assert len({(r['address_normalized'],r['entity_key']) for r in ledger})==len(ledger)
    assert all(r['raw_ref'] and r['source_url'] for r in ledger)
    assert all((r['listed_date'] and r['listed_action_url']) or (r['listed_date_method']=='unknown' and r['listed_date_reason']) for r in ledger)
    return ledger,addresses,actions_out,report,actions,manifest

def refresh():
    from collect_history import collect, collect_actions
    for key,url in OFFICIAL.items():
        fetch(key,url,refresh=True)
    for key,url in HISTORICAL.items():
        fetch(key,url)
    collect(refresh=True)
    collect_actions(refresh=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true',help='Refresh official XML, GitHub refs, sitemap and newly discovered actions')
    parser.add_argument('--check',action='store_true',help='Offline byte-for-byte comparison with saved CSV outputs; do not write')
    parser.add_argument('--report-json',action='store_true',help='Print computed acceptance counts')
    args = parser.parse_args()
    if args.fetch and args.check:
        parser.error('--check is offline; run --fetch separately')
    if args.fetch:
        refresh()
    ledger,addresses,actions,report,pages,manifest = derive()
    from report import render
    outputs = {'data/ledger.csv':csv_bytes(ledger),'data/addresses.csv':csv_bytes(addresses),
               'data/actions.csv':csv_bytes(actions),
               'docs/LEDGER.md':render(ledger,addresses,actions,report,pages,manifest)}
    changed = []
    for rel,body in outputs.items():
        path = ROOT/rel
        if not path.exists() or path.read_bytes()!=body:
            changed.append(rel)
            if args.check:
                old = path.read_text().splitlines() if path.exists() else []
                diff = difflib.unified_diff(old,body.decode().splitlines(),fromfile=rel,tofile='recomputed/'+rel,n=1)
                print('\n'.join(list(diff)[:30]))
            else:
                atomic(path,body)
    if args.report_json:
        print(json.dumps(report,indent=2,sort_keys=True))
    print(f'{len(ledger)} address–entity rows; {len(addresses)} chain–address rows; {len(actions)} action dates; '
          f'{sum(r["listed_date_method"]=="unknown" for r in ledger)} unknown listing dates; '
          f'{sum(r["status"]=="delisted" for r in ledger)} delisted rows')
    if args.check:
        if changed:
            print('CHECK FAILED: '+', '.join(changed),file=sys.stderr)
            return 1
        print('CHECK PASSED: all 3 CSVs and docs/LEDGER.md reproduce byte-for-byte offline')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
