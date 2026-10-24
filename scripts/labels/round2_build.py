"""Reproduce supplemental labels from saved, destination-specific evidence only.

Does not install the SQLite index. round2_report.py --install does that after
evidence and coverage validation, as the final atomic publication step.
"""
import argparse
import csv
import gzip
import html
import io
import json
import re
from html.parser import HTMLParser

from build import FIELDS
from policy import normalize_address
from round2_common import ROOT, RAW, OUT, atomic, read_json, save_json, sha


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('title', 'data-bs-title') and value and value.startswith('Public Name Tag (viewable by anyone)'):
                text = re.sub('<[^>]+>', ' ', html.unescape(value))
                text = text.removeprefix('Public Name Tag (viewable by anyone)').strip()
                name = re.sub(r'\s*\(0x[0-9a-fA-F]{40}\)\s*$', '', text).strip()
                if name:
                    self.names.append(name)


def public_names(body):
    parser = Tags()
    parser.feed(body.decode(errors='replace'))
    return sorted(set(parser.names))


def eth_role(name):
    """Explicit public labels only; never infer a numbered exchange wallet role."""
    if re.match(r'^(Binance|Gate|Bitget|OKX|KuCoin) Deposit:', name):
        return 'cex_deposit'
    if re.match(r'^(?:Uniswap.*(?:Router|USDC)|SushiSwap: Router|0x: Exchange Proxy|Aggregation Router V5)', name):
        return 'dex'
    if name == 'Tornado.Cash: Router' or re.match(r'^Tornado.Cash: .*\b(?:ETH|DAI|USDC|USDT|WBTC)\b', name):
        return 'mixer'
    if name in ('Aztec: Private Rollup Bridge', 'Avalanche: Old Bridge', 'Base: Base Bridge', 'Optimism: Gateway'):
        return 'bridge'
    if name == 'Wrapped Ether':
        return 'defi_other'
    if name in ('Binance 14', 'zkSync', 'Bridgers', 'OpenSea: Wyvern Exchange v1'):
        return 'unknown_service'
    return None


def rows_from_evidence():
    rows = []
    checks = []

    def add(chain, address, name, role, source, ref, url, locator, confidence='medium', notes='', valid_from='', valid_to='', entity=''):
        rows.append(dict(zip(FIELDS, [chain, normalize_address(chain, address), name, role, entity or name,
            source, ref, confidence, notes, 'r2_' + locator['kind'], url, ref,
            json.dumps(locator, sort_keys=True, separators=(',', ':')),
            'Public factual label; no open-data redistribution license established' if source != 'OFAC ledger (Round 2 frozen input)' else 'US government sanctions facts',
            valid_from, valid_to])))

    for source in ('etherscan_public', 'blockscout', 'tronscan', 'walletexplorer'):
        for record in read_json(RAW / (source + '_checks.json.gz')):
            body = gzip.decompress((ROOT / record['raw_ref']).read_bytes())
            assert sha(body) == record['sha256']
            evidence = []
            if record['http_status'] != 200:
                checks.append(dict(record, outcome='HTTP failure; no absence inference'))
                continue
            if source == 'etherscan_public':
                names = public_names(body)
                for name in names:
                    role = eth_role(name)
                    if role:
                        add('ETH', record['address'], name, role, 'Etherscan public address name tag', record['raw_ref'], record['url'],
                            {'kind': 'etherscan', 'name': name}, notes='Public address name tag, not a counterparty-table label. Historical service validity unverified. A generic exchange number establishes no deposit/hot-wallet role.')
                        evidence.append([name, role])
                outcome = 'public name tag checked' if names else 'no public name tag found in retrieved address page'
            else:
                obj = json.loads(body)
                if source == 'tronscan':
                    # The account self-name, owned tokens, and token spam never count.
                    name = obj.get('addressTag') or obj.get('publicTag')
                    if isinstance(name, str) and name:
                        role = 'cex_hot' if re.match(r'^Binance-Hot\s+\d+$', name) else 'unknown_service'
                        add('TRX', record['address'], name, role, 'TronScan public account addressTag', record['raw_ref'], record['url'],
                            {'kind': 'tronscan', 'field': 'addressTag' if obj.get('addressTag') else 'publicTag', 'name': name},
                            notes='Explorer public tag only; account self-name excluded. Historical role and ownership unverified.')
                        evidence.append([name, role])
                    outcome = 'public tag checked' if evidence else 'no nonempty addressTag/publicTag; self-names and token names excluded'
                elif source == 'blockscout':
                    for index, tag in enumerate(obj.get('public_tags') or []):
                        if tag.get('label') == 'Bridge' and tag.get('address_hash', '').lower() == record['address'].lower():
                            add('ETH', record['address'], 'Blockscout public tag: Bridge', 'bridge', 'Blockscout public address metadata', record['raw_ref'], record['url'],
                                {'kind': 'blockscout', 'index': index, 'name': 'Bridge'},
                                notes='Explicit public Bridge tag for this exact address; contract self-name alone is not a service label. Historical operation unverified.')
                            evidence.append(['Bridge', 'bridge'])
                    outcome = 'public tags and metadata checked' if evidence else 'no usable public_tags/metadata service label; verified contract name alone excluded'
                else:
                    name = obj.get('label')
                    if isinstance(name, str) and name:
                        role = 'mixer' if re.match(r'^(HelixMixer|BitcoinFog|BitMixer.io)', name) else 'unknown_service'
                        add('BTC', record['address'], name, role, 'WalletExplorer address-lookup cluster label', record['raw_ref'], record['url'],
                            {'kind': 'walletexplorer', 'name': name}, confidence='low',
                            notes='WalletExplorer heuristic cluster label; stale names and clustering uncertainty. Cluster IDs without names are not service labels. No deposit/hot-wallet role inferred.')
                        evidence.append([name, role])
                    outcome = 'cluster name checked' if evidence else 'address lookup returned no public cluster name; numeric wallet ID is not a service label'
            checks.append(dict(record, outcome=outcome, accepted_labels=evidence))

    targets = {(r['chain'], r['address']) for r in read_json(RAW / 'targets.json.gz')}
    ref = 'data/raw/labels2/inputs/ledger.csv.gz'
    with gzip.open(ROOT / ref, 'rt', newline='') as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            if (row['chain'], row['address_normalized']) not in targets:
                continue
            add(row['chain'], row['address_normalized'], 'OFAC listed: ' + row['sdn_name'], 'other_sanctioned',
                'OFAC ledger (Round 2 frozen input)', ref, row.get('listed_action_url') or row['source_url'],
                {'kind': 'ofac', 'index': index, 'entity_uid': row['sdn_uid']}, confidence='high',
                notes='Exact ledger membership. Listed ' + (row['listed_date'] or 'unresolved') +
                '; do not apply before that date. Later designation is a retrospective destination fact, not sanctions status at transfer time. Upstream: ' + row['raw_ref'],
                valid_from=row['listed_date'], valid_to=row.get('delisted_date', ''), entity=row['sdn_name'])
    rows = sorted({tuple(row[f] for f in FIELDS): row for row in rows}.values(),
                  key=lambda r: (r['chain'], r['address_normalized'], r['source_id'], r['label'], r['class']))
    return rows, checks


def encoded(rows):
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    rows, checks = rows_from_evidence()
    body = encoded(rows)
    if args.check:
        assert (OUT / 'labels_extra.csv').read_bytes() == body
        assert read_json(OUT / 'round2_checks.json.gz') == checks
        print('PASS: supplemental labels and all recorded destination checks reproduce from raw responses')
    else:
        atomic(OUT / 'labels_extra.csv', body)
        save_json(OUT / 'round2_checks.json.gz', checks)
        print(json.dumps({'supplemental_label_rows': len(rows), 'checks': len(checks), 'sha256': sha(body)}))
