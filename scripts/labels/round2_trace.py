"""Extend frozen flow paths to >=95% of unlabelled seed USD, without writing analysis paths.

Reuses the analysis process’s reviewed History/follow functions read-only. All new
requests, path bundles and script digests belong to labels2. Original seed USD is
a path weight, never a claimed amount received downstream. Run before installing
extra labels so before/after path comparisons use identical observed paths.
"""
import argparse
import collections
import gzip
import json
import sys
from decimal import Decimal
from urllib.parse import urlsplit

from round2_common import ROOT, RAW, atomic, edges, fetch, ranked, read_json, save_json, sha

sys.path.insert(0, str(ROOT / 'scripts/analysis'))
import trace as upstream


class Client:
    def __init__(self, network):
        self.network = network
        self.requests = {}
        self.count = 0
        self.prior = read_json(RAW / 'inputs/trace_latest.json.gz')['requests']

    def get(self, url):
        url = upstream.canonical_url(url)
        if url in self.prior:
            ref = self.prior[url]
            envelope = read_json(ROOT / ref)
            self.requests[url] = ref
            if envelope['status'] != 200 or envelope.get('transport_error'):
                raise upstream.Gap('saved source HTTP failure')
            return envelope['response'], ref
        if urlsplit(url).netloc not in {'eth.blockscout.com', 'btc1.trezor.io', 'api.trongrid.io'}:
            raise upstream.Gap('route outside labels2 scope')
        cache = RAW / 'histories' / (sha(url.encode()) + '.json.gz')
        if cache.exists():
            envelope = read_json(cache)
        elif self.network:
            if self.count >= 400:
                raise upstream.Gap('labels2 request budget exhausted')
            body, meta = fetch(url)
            self.count += 1
            try:
                response = json.loads(body)
            except ValueError:
                response = {'unparsed_body': body[:1000].decode(errors='replace')}
            envelope = dict(meta, status=meta['http_status'], response=response)
            save_json(cache, envelope)
        else:
            raise upstream.Gap('labels2 offline cache miss')
        ref = str(cache.relative_to(ROOT))
        self.requests[url] = ref
        if envelope['status'] != 200:
            raise upstream.Gap('HTTP ' + str(envelope['status']) + ' ' + ref)
        return envelope['response'], ref


class History(upstream.History):
    def evm(self, chain, address, asset, lower_block, lower_time, decimals):
        # The legacy compatible route was unsupported in the original run;
        # use v2 with its existing reverse-pagination/ordering-proof rule.
        return self.evm_v2(chain, address, asset, lower_block, lower_time, decimals)


def run(network=False):
    # Freeze the classifier to the pre-round index claims. Installing new labels
    # must not shorten the evidence paths during offline reproduction.
    import csv
    baseline = collections.defaultdict(list)
    with gzip.open(RAW / 'inputs/labels.csv.gz', 'rt', newline='') as stream:
        for row in csv.DictReader(stream):
            baseline[row['chain'], row['address_normalized']].append(row)
    upstream.f.claims = lambda chain, address: baseline.get((chain, address), [])
    seed_edges = edges()
    for edge in seed_edges:
        edge['block'] = int(edge['block']) if edge['block'] else None
    unknown = [e for e in seed_edges if e['destination_class'] == 'unlabelled']
    denominator = sum((Decimal(e['usd']) for e in unknown), Decimal(0))
    selected, amount = set(), Decimal(0)
    for row in ranked():
        if row['address'].startswith('__'):
            continue
        group = [e for e in unknown if (e['chain'], e['destination_address']) == (row['chain'], row['address'])]
        if not group:
            continue
        selected.update(e['edge_id'] for e in group)
        amount += sum((Decimal(e['usd']) for e in group), Decimal(0))
        if amount >= denominator * Decimal('.95'):
            break
    # Also investigate 95% within each chain. Synthetic destinations cannot be
    # queried; keep them in denominators and expose any unmet chain target.
    per_chain = {}
    for chain in sorted({e['chain'] for e in unknown}):
        subtotal = sum((Decimal(e['usd']) for e in unknown if e['chain'] == chain), Decimal(0))
        running = Decimal(0)
        for row in ranked():
            if row['chain'] != chain or row['address'].startswith('__'):
                continue
            group = [e for e in unknown if (e['chain'], e['destination_address']) == (chain, row['address'])]
            if not group:
                continue
            selected.update(e['edge_id'] for e in group)
            running += sum((Decimal(e['usd']) for e in group), Decimal(0))
            if running >= subtotal * Decimal('.95'):
                break
        per_chain[chain] = {'unlabelled_usd': str(subtotal), 'selected_usd': str(running),
                            'selected_share': str(running / subtotal) if subtotal else None}
    ordered = sorted((e for e in unknown if e['edge_id'] in selected),
                     key=lambda e: (e['time_utc'], int(e.get('block') or 0), e['hash'], e['edge_id']))
    amount = sum((Decimal(e['usd']) for e in ordered), Decimal(0))
    client, paths, reserved = Client(network), [], set()
    history = History(client)
    for i, edge in enumerate(ordered):
        path = upstream.follow(edge, history, {}, reserved)
        paths.append(path)
        print(i + 1, len(ordered), edge['chain'], edge['destination_address'], path['status'], path.get('terminal_class'), client.count, flush=True)
    scripts = {p: sha((ROOT / p).read_bytes()) for p in ('scripts/analysis/trace.py', 'scripts/analysis/flows.py',
        'scripts/labels/lookup.py', 'scripts/labels/policy.py', 'scripts/prices/price.py')}
    return {'schema_version': 1, 'input_manifest': 'data/raw/labels2/inputs/manifest.json',
            'hop_rule': upstream.f.HOP_RULE, 'selection': {'target': '.95', 'unlabelled_seed_usd': str(denominator),
                'selected_seed_usd': str(amount), 'selected_share': str(amount / denominator),
                'per_chain': per_chain,
                'seed_addresses': len({(e['chain'], e['destination_address']) for e in ordered})},
            'scripts_sha256': scripts, 'paths': paths, 'requests': client.requests,
            'notes': ['Same-asset temporal heuristic, not downstream USD attribution.',
                'Comparisons reclassify the same frozen paths before/after labels; later OFAC membership is separate.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = run(args.fetch)
    target = RAW / 'trace95.json.gz'
    if args.check:
        # Script hashes describe the collection revision; label additions can
        # change current classification, so --check compares path event links.
        old = read_json(target)
        assert result['selection'] == old['selection']
        assert [(p['edge_id'], p['steps']) for p in result['paths']] == [(p['edge_id'], p['steps']) for p in old['paths']]
        print('PASS: selected seed weights and observed path events reproduce offline')
    else:
        save_json(target, result)
        print(json.dumps(result['selection']))
