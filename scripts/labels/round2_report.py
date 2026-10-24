"""Reproduce Round 2 value coverage and append docs/LABELS.md; install index last.

First-hop dollars retain each original transfer's saved historical price. Multi-
hop dollars are original receipt weights, not downstream amounts or unique funds.
Unknown service names remain separate from supported destination-role classes.
"""
import argparse
import collections
import csv
import gzip
import io
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from build import FIELDS, build_index, index_rows
from policy import CLASSES, ADDITIONAL_CLASSES
from round2_common import ROOT, RAW, OUT, atomic, edges, ranked, read_json, save_json, sha
from round2_build import encoded, eth_role, public_names, rows_from_evidence

ROLES = set(CLASSES + ADDITIONAL_CLASSES) - {'unknown_service', 'scam_poisoning'}
MARKER = '\n## Round 2\n'


def table(headers, rows):
    clean = lambda v: str(v).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |'] +
                     ['| ' + ' | '.join(clean(c) for c in row) + ' |' for row in rows])


def usd(value):
    return f'${Decimal(value):,.2f}'


def share(value, denominator):
    return f'{Decimal(value) / Decimal(denominator):.4%}' if Decimal(denominator) else 'n/a'


def date(value):
    if not value:
        return None
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return result.replace(tzinfo=ZoneInfo('America/New_York')) if len(value) == 10 else result.astimezone(timezone.utc)


def load_labels():
    with gzip.open(RAW / 'inputs/labels.csv.gz', 'rt', newline='') as stream:
        base = list(csv.DictReader(stream))
    extra, _ = rows_from_evidence()
    assert encoded(extra) == (OUT / 'labels_extra.csv').read_bytes()
    maps = []
    for rows in (base, base + extra):
        mapping = collections.defaultdict(list)
        for row in rows:
            mapping[row['chain'], row['address_normalized']].append(row)
        maps.append(mapping)
    return base, extra, maps


def classify(mapping, chain, address, when, retrospective=False):
    applicable = []
    for row in mapping.get((chain, address), []):
        if row['class'] not in ROLES:
            continue
        if row['class'] == 'other_sanctioned':
            start, end = date(row['valid_from']), date(row['valid_to'])
            if not start:
                continue
            if when < start:
                if not retrospective:
                    continue
            elif end and when >= end:
                continue
        applicable.append(row)
    functional = sorted({r['class'] for r in applicable if r['class'] != 'other_sanctioned'})
    role = 'unlabelled' if len(functional) > 1 else functional[0] if functional else 'other_sanctioned' if applicable else 'unlabelled'
    return role, [r for r in applicable if r['class'] == role]


def reached(mapping, edge, path=None, retrospective=False):
    observations = [(edge['destination_address'], edge['time_utc'])]
    if path:
        assert len(path['steps']) <= 4
        observations += [(s['to'], s['time_utc']) for s in path['steps']]
    for hop, (address, when) in enumerate(observations, 1):
        role, claims = classify(mapping, edge['chain'], address, date(when), retrospective)
        if role != 'unlabelled':
            return {'class': role, 'address': address, 'hop': hop,
                    'labels': sorted({r['label'] for r in claims}),
                    'raw_refs': sorted({r['raw_ref'] for r in claims})}
    return None


def totals(rows, maps, paths):
    by_id = {p['edge_id']: p for p in paths}
    output = []
    for chain in ['ALL'] + sorted({r['chain'] for r in rows}):
        selected = [r for r in rows if chain == 'ALL' or r['chain'] == chain]
        total = sum((Decimal(r['usd']) for r in selected), Decimal(0))
        traced = [r for r in selected if r['edge_id'] in by_id]
        denominator = sum((Decimal(r['usd']) for r in traced), Decimal(0))
        record = {'chain': chain, 'first_hop_total_usd': str(total), 'first_hop_events': len(selected),
                  'traced_seed_usd': str(denominator), 'traced_receipt_paths': len(traced),
                  'raw_ref': 'data/raw/labels2/inputs/flows_edges_included.csv.gz'}
        for prefix, mapping in zip(('before', 'after'), maps):
            for mode in ('first_hop', 'traced', 'all_reachable', 'retrospective_first_hop'):
                pool = traced if mode == 'traced' else selected
                value = Decimal(0)
                for row in pool:
                    hit = reached(mapping, row, by_id.get(row['edge_id']) if mode in ('traced', 'all_reachable') else None,
                                  retrospective=mode == 'retrospective_first_hop')
                    if hit:
                        value += Decimal(row['usd'])
                record[prefix + '_' + mode + '_labelled_usd'] = str(value)
        output.append(record)
    return output


def destination_records(rows, maps, checks):
    groups = collections.defaultdict(list)
    per_address = collections.defaultdict(list)
    ranks = collections.Counter()
    for row in rows:
        groups[row['chain'], row['destination_address']].append(row)
    for check in checks:
        per_address[check['chain'], check['address']].append(check)
    output = []
    for rank, item in enumerate(ranked(), 1):
        chain, address = item['chain'], item['address']
        ranks[chain] += 1
        es = groups[chain, address]
        claims = maps[1].get((chain, address), [])
        names = sorted({r['label'] + ' [' + r['class'] + (', listed ' + r['valid_from'] if r['class'] == 'other_sanctioned' else '') + ']' for r in claims})
        checked = per_address[chain, address]
        before = sum((Decimal(e['usd']) for e in es if reached(maps[0], e)), Decimal(0))
        after = sum((Decimal(e['usd']) for e in es if reached(maps[1], e)), Decimal(0))
        output.append(dict(item, global_rank=rank, chain_rank=ranks[chain], receipt_events=len(es),
            before_labelled_usd=str(before), after_labelled_usd=str(after),
            label='; '.join(names) if names else 'unallocated destination; not an address' if address.startswith('__') else 'no public label found',
            label_source='; '.join(sorted({r['label_source'] for r in claims})),
            source_url='; '.join(sorted({r['source_url'] for r in claims} or {r['url'] for r in checked})),
            raw_ref='; '.join(sorted({r['raw_ref'] for r in claims} or {r['raw_ref'] for r in checked} or {e['raw_ref'] for e in es})),
            checked='; '.join(sorted({r['source'] + ': ' + r['outcome'] for r in checked})),
            flow_raw_refs='; '.join(sorted({e['raw_ref'] for e in es}))))
    return output


def summary_and_records():
    manifest = read_json(RAW / 'inputs/manifest.json')
    base, extra, maps = load_labels()
    es = edges()
    for e in es:
        role, _ = classify(maps[0], e['chain'], e['destination_address'], date(e['time_utc']))
        if role == 'unlabelled' and e['self_transfer_same_entity'] == 'True':
            role = 'other_sanctioned'
        assert role == e['destination_class'], 'Baseline class mismatch for ' + e['edge_id']
    original = read_json(RAW / 'inputs/trace_latest.json.gz')
    expanded = read_json(RAW / 'trace95.json.gz')
    checks = read_json(OUT / 'round2_checks.json.gz')
    # Every real ETH/BTC/TRX first-hop destination has a chain-specific check.
    checked_keys = {(r['chain'], r['address']) for r in checks if r['http_status'] == 200}
    expected = {(e['chain'], e['destination_address']) for e in es
                if e['chain'] in {'BTC', 'ETH', 'TRX'} and not e['destination_address'].startswith('__')}
    assert expected <= checked_keys
    unknown = sum((Decimal(e['usd']) for e in es if e['destination_class'] == 'unlabelled'), Decimal(0))
    investigated = sum((Decimal(e['usd']) for e in es if e['destination_class'] == 'unlabelled' and
                        (e['chain'], e['destination_address']) in checked_keys), Decimal(0))
    assert investigated / unknown >= Decimal('.95')
    data = {'unit': 'USD at each original first-hop transfer time; trace values are original receipt weights',
        'snapshot_at': read_json(RAW / 'inputs/flows.json.gz')['snapshot_at'],
        'input_manifest': 'data/raw/labels2/inputs/manifest.json', 'extra_label_rows': len(extra),
        'extra_chain_addresses': len({(r['chain'], r['address_normalized']) for r in extra}),
        'new_chain_addresses': len({(r['chain'], r['address_normalized']) for r in extra} - {(r['chain'], r['address_normalized']) for r in base}),
        'base_rows': len(base), 'index_rows': len(index_rows(base)),
        'extra_by_class': dict(collections.Counter(r['class'] for r in extra)),
        'source_check_count': len(checks), 'source_check_chain_addresses': len(checked_keys),
        'first_hop_real_chain_addresses': len(expected), 'unlabelled_first_hop_usd': str(unknown),
        'investigated_unlabelled_usd': str(investigated), 'investigated_share': str(investigated / unknown),
        'extended_trace_selection': expanded['selection'],
        'original_trace_ref': original['bundle_ref'], 'extended_trace_ref': 'data/raw/labels2/trace95.json.gz',
        'original_paths': totals(es, maps, original['paths']), 'expanded_paths': totals(es, maps, expanded['paths']),
        'path_status_counts': dict(collections.Counter(p['status'] for p in expanded['paths'])),
        'raw_ref': 'data/raw/labels2/inputs/flows_edges_included.csv.gz',
        'source_url': 'results/flows.json (frozen snapshot; per-transfer upstream URLs in raw_ref)'}
    return data, destination_records(es, maps, checks), (es, maps, original, expanded, extra)


def source_cell(record, details):
    _, maps, _, _, _ = details
    chain, address = record['chain'], record['address']
    claims = maps[1].get((chain, address), [])
    if claims:
        chosen = sorted(claims, key=lambda r: (r['confidence'] != 'high', not r['source_id'].startswith('r2_'), r['source_id']))[0]
        text = '; '.join(sorted({r['label'] + ' / ' + r['class'] + (' (listed ' + r['valid_from'] + ')' if r['class'] == 'other_sanctioned' else '') for r in claims}))
        return text, '[' + chosen['label_source'].split(' @ ')[0] + '](' + chosen['source_url'] + ')'
    if address.startswith('__'):
        return 'unallocated destination; not an address', 'frozen flow edge; output allocation unavailable'
    if chain == 'BTC':
        return 'no public label found', '[WalletExplorer address lookup](https://www.walletexplorer.com/api/1/address-lookup?address=' + address + '); no cluster name' + ('; [DOJ complaint](https://www.justice.gov/usao-edny/media/1416291/dl) has no exact destination match' if record['chain_rank'] <= 4 else '')
    if chain == 'ETH':
        return 'no public label found', '[Blockscout](https://eth.blockscout.com/api/v2/addresses/' + address + ') public tags/metadata; [Etherscan](https://etherscan.io/address/' + address + ') public name tag'
    if chain == 'TRX':
        return 'no public label found', '[TronScan](https://apilist.tronscanapi.com/api/account?address=' + address + ') addressTag/publicTag; self-name excluded'
    return 'no public label found', 'frozen OFAC/label-registry exact match checked; Blockchair blocked (HTTP 430); no usable alternate tag source'


def render(summary, records, details):
    es, maps, original, expanded, extra = details
    all_old, all_new = summary['original_paths'][0], summary['expanded_paths'][0]
    total = Decimal(all_new['first_hop_total_usd'])
    lines = ['', 'This round adds **' + str(len(extra)) + ' source claims** for **' + str(summary['extra_chain_addresses']) +
        ' chain/address pairs** (' + str(summary['new_chain_addresses']) + ' pairs absent from the frozen base). The lookup index contains **' + str(summary['index_rows']) +
        ' rows**, combining the unchanged Round 1 `labels.csv` with `labels_extra.csv`. Label claims are leads; none establishes unlawful conduct or inferred address control.', '',
        f"The audited flow snapshot is `{summary['snapshot_at']}`: **{usd(total)}** across **{all_new['first_hop_events']:,} included first-hop transfer edges**, using each edge's saved price observation at or before transfer time. "
        'The full selected edge rows, prices, upstream transaction URLs and raw references are frozen in `data/raw/labels2/inputs/flows_edges_included.csv.gz`; `inputs/manifest.json` records the shared CSV size, modification time, filter and selected-content digest. Analyses and result files were read only.', '',
        f"Destination-specific public lookups cover **{share(summary['investigated_unlabelled_usd'], summary['unlabelled_first_hop_usd'])} of unlabelled first-hop USD** ({usd(summary['investigated_unlabelled_usd'])}/{usd(summary['unlabelled_first_hop_usd'])}). "
        f"There are **{summary['source_check_count']} saved explorer lookups** across **{summary['source_check_chain_addresses']} chain/address pairs**, including every real BTC, ETH and TRX first-hop destination and all observed trace nodes. "
        'This is investigation coverage, not the share successfully labelled. Synthetic mixed-input/unresolved destinations have no address to query.', '',
        '### First-hop labelled share: same transfers before and after', '',
        '`other_sanctioned` counts only within its saved listing interval at the transfer date. Service roles use the public functional label, whose transaction-time validity is generally unverified. Generic exchange numbers and `unknown_service` do not count as supported destination roles. Later OFAC listing is shown separately below.', '',
        table(['Chain', 'First-hop USD at transfer times', 'Before labelled USD / share', 'After labelled USD / share'],
            [[r['chain'], usd(r['first_hop_total_usd']), usd(r['before_first_hop_labelled_usd']) + ' / ' + share(r['before_first_hop_labelled_usd'], r['first_hop_total_usd']),
              usd(r['after_first_hop_labelled_usd']) + ' / ' + share(r['after_first_hop_labelled_usd'], r['first_hop_total_usd'])] for r in summary['expanded_paths']]), '',
        '### Up to five hops: original trace held fixed', '',
        'Each USD figure below is the original first-hop receipt weight, counted once per receipt path if it reaches any supported label within the observed prefix. It is **not an amount proven received downstream**, a unique-funds total, or balance-aware taint accounting. Hop 1 is the initial receipt. The original active bundle is `' + summary['original_trace_ref'] + '`.', '',
        table(['Chain', 'Original traced seed USD', 'Before reaches label / share', 'After reaches label / share'],
            [[r['chain'], usd(r['traced_seed_usd']), usd(r['before_traced_labelled_usd']) + ' / ' + share(r['before_traced_labelled_usd'], r['traced_seed_usd']),
              usd(r['after_traced_labelled_usd']) + ' / ' + share(r['after_traced_labelled_usd'], r['traced_seed_usd'])] for r in summary['original_paths']]), '',
        '### Expanded paths and separation of label gains from trace gains', '',
        f"The extension attempts **{summary['extended_trace_selection']['seed_addresses']} destination addresses / {all_new['traced_receipt_paths']} receipt paths**, representing **{share(summary['extended_trace_selection']['selected_seed_usd'], summary['extended_trace_selection']['unlabelled_seed_usd'])} of originally unlabelled first-hop USD**. "
        'It also targets 95% of unlabelled value within each chain. LTC and XRP are entirely synthetic/unresolved destinations and cannot meet that address-selection target. BCH targets are selected but the checked history route is unsupported. The extension reuses the analysis module\'s History/follow functions read only, freezes the pre-round label claims, and saves every new response under labels2. Native EVM v2 requires reverse pagination sufficient to prove earliest observed order; same-time ambiguity, cycles, pagination gaps and five-hop stops remain explicit.', '',
        'Both columns below reclassify the **same expanded observed paths**. Their difference is due to new label evidence. The increase from the previous table also includes additional paths and must not be presented as label improvement alone.', '',
        table(['Chain', 'Expanded traced seed USD', 'Before labels: reaches / share', 'After labels: reaches / share'],
            [[r['chain'], usd(r['traced_seed_usd']), usd(r['before_traced_labelled_usd']) + ' / ' + share(r['before_traced_labelled_usd'], r['traced_seed_usd']),
              usd(r['after_traced_labelled_usd']) + ' / ' + share(r['after_traced_labelled_usd'], r['traced_seed_usd'])] for r in summary['expanded_paths']]), '',
        'As a share of **all first-hop outflow USD**, counting a receipt once if labelled at hop 1 or in its observed path: ' +
        share(all_old['before_all_reachable_labelled_usd'], total) + ' with the original paths/base labels; ' +
        share(all_new['before_all_reachable_labelled_usd'], total) + ' with expanded paths/base labels; ' +
        share(all_new['after_all_reachable_labelled_usd'], total) + ' with expanded paths/new labels. Untraced or unresolved receipts remain in the denominator. Original receipt weights can recirculate and are not unique economic value.', '',
        '### Later OFAC designations', '',
        'A separate retrospective view asks whether the recipient was listed later. Its first-hop known-class share after this round is **' + share(all_new['after_retrospective_first_hop_labelled_usd'], total) +
        '** (' + usd(all_new['after_retrospective_first_hop_labelled_usd']) + '). It must not be substituted for the as-of-transfer table. The seven large Lazarus recipients already existed in the Round 1 ledger labels; new current explorer checks corroborate the tags without moving their listing dates backward. Exact dates and row evidence are in `labels_extra.csv` and `round2_destinations.csv`.', '',
        table(['Chain', 'Before retrospective first-hop labelled share', 'After retrospective first-hop labelled share'],
            [[r['chain'], share(r['before_retrospective_first_hop_labelled_usd'], r['first_hop_total_usd']), share(r['after_retrospective_first_hop_labelled_usd'], r['first_hop_total_usd'])]
             for r in summary['expanded_paths']]), '',
        '### Largest 20 first-hop destinations, all chains', '',
        'Dollar totals sum first-hop transfer edges at their respective historical prices. Labels below may describe later designation; they do not alter the as-of-transfer rule. Every row\'s exact raw label/check references and underlying transaction references are retained in `data/labels/round2_destinations.csv`.', '',
        table(['Rank', 'Chain / destination', 'First-hop USD', 'Public label / class', 'Source or checks'],
            [[r['global_rank'], r['chain'] + ' `' + r['address'] + '`', usd(r['usd']), *source_cell(r, details)] for r in records[:20]])]
    for chain in sorted({r['chain'] for r in records}):
        lines += ['', '### ' + chain + ': top 20 first-hop destinations (or all if fewer)', '',
            table(['Chain rank', 'Destination', 'First-hop USD', 'Public label / class', 'Source or checks'],
                [[r['chain_rank'], '`' + r['address'] + '`', usd(r['usd']), *source_cell(r, details)] for r in records if r['chain'] == chain and r['chain_rank'] <= 20])]
    node_weights = collections.defaultdict(Decimal)
    node_times = {}
    for path in expanded['paths']:
        edge = next(e for e in es if e['edge_id'] == path['edge_id'])
        seen = set()
        for address, when in [(edge['destination_address'], edge['time_utc'])] + [(s['to'], s['time_utc']) for s in path['steps']]:
            key = path['chain'], address
            if key not in seen:
                node_weights[key] += Decimal(edge['usd'])
                node_times.setdefault(key, when)
                seen.add(key)
    nodes = sorted(node_weights, key=lambda k: (-node_weights[k], k))[:20]
    lines += ['', '### Largest 20 trace nodes by original receipt weights', '',
        'An address receives each path\'s original seed weight once in this ranking. Several nodes can be on the same path: **these rows overlap and must never be summed**. They are not the USD value transferred into those nodes. Node-specific label probes, response timestamps and raw references are in `round2_checks.json.gz`; transfer links are in `trace95.json.gz`.', '',
        table(['Chain / node', 'Overlapping original receipt USD weight', 'Public label / class', 'Source or checks'],
            [[chain + ' `' + address + '`', usd(node_weights[chain, address]),
              *source_cell({'chain': chain, 'address': address, 'chain_rank': 0}, details)] for chain, address in nodes]), '',
        '### Sources, negative findings and limits', '',
        '- **BTC government documents:** the DOJ [civil complaint](https://www.justice.gov/usao-edny/media/1416291/dl), case 1:25-cv-05745-BMC, Attachment A (page 42), names 25 historical storage addresses. Page 23 footnote 7 and page 37 paragraph 58 say the cryptocurrency moved to other addresses and is in U.S. custody. None of the first-hop destinations here matches Attachment A; the document does not name the four large destination addresses. Pages 23, 37 and 42 were rendered and visually checked. No `government_seizure` label is assigned by transaction linkage or inferred custody. The new class is supported by the supplemental schema, but this round has **zero supported destination rows** for it. The October 8 indictment is saved independently. Discovery uses the [DOJ public press-release API](' +
        'https://www.justice.gov/api/v1/press_releases.json?parameters%5Btitle%5D=Chairman%20of%20Prince%20Group' + '), whose attachment IDs resolve the documents. Raw PDFs are gzip objects; extracted pages, API responses and negative exact-address checks are under `data/raw/labels2/`.',
        '- **BTC explorers:** WalletExplorer was queried by every destination address, rather than taking only the first 100 addresses in a named cluster. Unnamed numeric wallet IDs are not service labels. Its one named Huobi cluster remains low-confidence `unknown_service` because deposit/hot role is unspecified. Blockchair returned HTTP 430 on the first probe; requests stopped. The 20 mempool address pages returned an application shell without server-rendered tag data. These availability failures do not prove absence of labels. The four largest BTC paths have no later outgoing transfer in the original checked history; this is bounded evidence, not permanent stillness or unknown-controller identification.',
        '- **ETH:** saved Blockscout `/api/v2/addresses/{address}` metadata/public tags and Etherscan address-page Public Name Tag fields were checked for every destination and trace node. The name-tag parser excludes transaction counterparties, held-token names, contract self-names, ENS names and risk allegations. Explicit deposit wording is accepted; `Binance 14` remains an unknown wallet role. No paid Etherscan name-tag endpoint or API key was used. Existing official protocol registries remain citable base sources; current public tags add bridge classifications only where the role is explicit. The wrapped ETH token contract is `defi_other`, so the existing site taxonomy may still fold it into unlabelled.',
        '- **Open repositories:** GitHub metadata/branch-tip responses confirm both brianleect/etherscan-labels and dawsbot/eth-labels still resolve to the pinned Round 1 revisions. Their saved immutable registry files were reused; no new upstream code or dependency was executed. The metadata and digests are saved in `supplement.json` and `requests/`.',
        '- **TRX:** account `addressTag`/`publicTag` fields were checked for every destination and observed trace node. `Binance-Hot 7` is an explicit hot-wallet role; `MXC 2` is a service name with unresolved wallet role. Self-names, token spam, and the SmartExchangeRouter self-name are not service attribution. `accountv2` returned 401; no authorization bypass was attempted. No checked recipient had a usable Tether treasury, issuer burn or Justin Sun treasury public tag, so no ownership/issuer labels were invented. One observed path prefix reaches the newly labelled Binance wallet before its next-step ordering gap.',
        '- **BCH/LTC/XRP:** no usable new service tag was established. BCH real recipients were checked against the frozen OFAC/service registry; the external Blockchair source was blocked and the selected history route was out of scope. LTC and XRP flow dollars here are synthetic unresolved destinations, not queryable address strings. Their gaps remain in denominators.',
        '- **Temporal and value limits:** OFAC date-only boundaries use America/New_York midnight as in the flow analysis; exact publication-time ambiguity remains. Service labels usually lack historical validity. No wallet-cluster propagation, guessed ownership, asset conversion, bridge continuation, USD revaluation, or mixed-input output allocation is introduced. `government_seizure` requires an exact address in a government source with a supported seizure/forfeiture/custody statement.', '',
        'This is the labels2 coverage note within the job\'s owned documentation; the integrator may append it to shared `docs/COVERAGE.md`. This is research, not legal or compliance advice. Receiving funds from a sanctioned address does not establish unlawful conduct; services may have frozen or reported funds.', '',
        '### Reproduction and acceptance checks', '',
        '```sh',
        '.venv/bin/python -S scripts/labels/round2_common.py',
        '.venv/bin/python -S scripts/labels/round2_trace.py --fetch',
        '.venv/bin/python -S scripts/labels/round2_collect.py',
        '.venv/bin/python -S scripts/labels/round2_supplement.py',
        '.venv/bin/python -S scripts/labels/round2_build.py',
        '.venv/bin/python -S scripts/labels/round2_report.py --install', '',
        '# Offline, without modifying outputs or calling external services:',
        '.venv/bin/python -S scripts/labels/round2_build.py --check',
        '.venv/bin/python -S scripts/labels/round2_trace.py --check',
        '.venv/bin/python -S scripts/labels/round2_report.py --check',
        '.venv/bin/python -S scripts/labels/build.py --check',
        '.venv/bin/python -S scripts/labels/validate.py --check',
        '.venv/bin/python -S scripts/labels/report.py --check',
        '```', '',
        '`round2_report.py --check` reproduces all value tables, every ranked destination row and this appended section; validates HTTP/raw digests, the frozen input manifest, label provenance, path edge identities, class conflicts, later-designation timing and index rows; and checks SQLite integrity and source-row preservation. The installed index is replaced atomically only after validation. `lookup.label(chain,address)` retains its interface and returns all source claims, including dated future designations. Consumers must apply temporal validity themselves. The original analysis/site hard-coded class lists do not yet include `government_seizure`; no downstream code was changed. Existing pipeline rebuilds incorporate `labels_extra.csv` through `build.py`; labels alone do not refresh already generated flow results.', '']
    return '\n'.join(lines)


def csv_records(records):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue().encode()


def validate_inputs(summary, details):
    manifest = read_json(RAW / 'inputs/manifest.json')
    for path, entry in manifest['inputs'].items():
        body = (ROOT / entry['raw_ref']).read_bytes()
        payload = body if path.endswith('.gz') else gzip.decompress(body)
        assert sha(payload) == entry.get('sha256', entry.get('selection_sha256')), path
    for path in (RAW / 'requests').glob('*.json'):
        meta = read_json(path)
        assert sha(gzip.decompress((ROOT / meta['raw_ref']).read_bytes())) == meta['sha256']
        assert not any(x in meta['request']['url'].lower() for x in ('apikey=', 'api_key=', 'token='))
    for path in (RAW / 'histories').glob('*.json.gz'):
        envelope = read_json(path)
        body = gzip.decompress((ROOT / envelope['raw_ref']).read_bytes())
        assert sha(body) == envelope['sha256']
        try:
            decoded = json.loads(body)
        except ValueError:
            decoded = {'unparsed_body': body[:1000].decode(errors='replace')}
        assert decoded == envelope['response']
    government = read_json(RAW / 'government_checks.json.gz')
    assert government['schedule_address_count'] == 25
    assert not any(r['named_in_attachment_a'] for r in government['checks'])
    es, maps, original, expanded, extra = details
    ids = {e['edge_id']: e for e in es}
    for bundle in (original, expanded):
        assert len({p['edge_id'] for p in bundle['paths']}) == len(bundle['paths'])
        for p in bundle['paths']:
            e = ids[p['edge_id']]
            assert Decimal(e['usd']) == Decimal(p['seed_usd'])
            assert (e['chain'], e['destination_address']) == (p['chain'], p['seed_address'])
            assert len(p['steps']) <= 4
            addr = e['destination_address']
            for step in p['steps']:
                assert step['from'] == addr and step['chain'] == e['chain'] and step['asset'] == e['asset']
                assert (ROOT / step['raw_ref'].split('#')[0]).is_file()
                addr = step['to']
    # Meaningful safeguards against temporal leakage and numeric-wallet naming.
    test = {'class': 'other_sanctioned', 'valid_from': '2025-01-02', 'valid_to': '', 'label': 'test'}
    mapping = {('ETH', 'a'): [test]}
    assert classify(mapping, 'ETH', 'a', date('2025-01-01T00:00:00Z'))[0] == 'unlabelled'
    assert classify(mapping, 'ETH', 'a', date('2025-01-01T00:00:00Z'), True)[0] == 'other_sanctioned'
    assert public_names(b'<a title="Binance Deposit: counterparty">x</a>') == []
    assert public_names(b'<span title="Public Name Tag (viewable by anyone) &lt;br/&gt; Binance Deposit: 0x1111111111111111111111111111111111111111&#10;(0x1111111111111111111111111111111111111111)"></span>') == ['Binance Deposit: 0x1111111111111111111111111111111111111111']
    assert eth_role('Binance 14') == 'unknown_service'
    assert eth_role('Binance Deposit: 0xa01bd7860cbb705a1a0c9bf4c98470516462b71f') == 'cex_deposit'
    assert eth_role('Fake_Phishing123') is None
    assert 'government_seizure' in CLASSES
    assert all(r['label_source'] and r['source_ref'] == r['raw_ref'] for r in extra)
    assert not any(r['class'] == 'government_seizure' for r in extra)


def check_index(base):
    expected = index_rows(base)
    with sqlite3.connect((OUT / 'labels.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT * FROM labels ORDER BY rowid').fetchall() == [tuple(r[f] for f in FIELDS) for r in expected]
        assert db.execute("SELECT value FROM metadata WHERE key='extras_sha256'").fetchone()[0] == sha((OUT / 'labels_extra.csv').read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    summary, records, details = summary_and_records()
    validate_inputs(summary, details)
    section = render(summary, records, details)
    target = ROOT / 'docs/LABELS.md'
    previous = target.read_text()
    prefix = previous.split(MARKER, 1)[0]
    document = prefix + MARKER + section
    if args.check:
        assert not args.install
        assert read_json(OUT / 'round2_summary.json') == summary
        assert (OUT / 'round2_destinations.csv').read_bytes() == csv_records(records)
        assert previous == document, 'Round 2 document drift'
        base, _, _ = load_labels()
        check_index(base)
        print('PASS: Round 2 coverage, destination ranks, document, raw evidence and atomic index')
    else:
        save_json(OUT / 'round2_summary.json', summary)
        atomic(OUT / 'round2_destinations.csv', csv_records(records))
        atomic(target, document.encode())
        if args.install:
            base, _, _ = load_labels()
            assert sha((OUT / 'labels.csv').read_bytes()) == read_json(RAW / 'inputs/manifest.json')['inputs']['data/labels/labels.csv']['sha256']
            build_index(base, sha((OUT / 'labels.csv').read_bytes()))
            check_index(base)
        print(json.dumps(summary['expanded_paths'][0], indent=2))
