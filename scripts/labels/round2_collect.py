"""Collect destination-specific public evidence; resumable, no private APIs or keys.

Run after round2_common.py. Sources are queried for every real first-hop address,
plus all nodes in the frozen active up-to-five-hop trace. Per-host workers are serial.
"""
import argparse
import concurrent.futures
import json
from urllib.parse import quote

from round2_common import RAW, fetch, ranked, read_json, save_json, snapshot


def targets():
    output = {(r['chain'], r['address']): dict(r, trace_node=False) for r in ranked()
              if not r['address'].startswith('__')}
    bundles = [read_json(RAW / 'inputs/trace_latest.json.gz')]
    if (RAW / 'trace95.json.gz').exists():
        bundles.append(read_json(RAW / 'trace95.json.gz'))
    for path in [p for bundle in bundles for p in bundle['paths']]:
        addresses = {path['seed_address'], path.get('terminal_address', '')}
        for step in path.get('steps', []):
            addresses.update((step['from'], step['to']))
        for address in addresses - {''}:
            key = path['chain'], address
            if key not in output:
                output[key] = {'chain': key[0], 'address': key[1], 'usd': '0'}
            output[key]['trace_node'] = True
    return list(output.values())


def collect_source(source, rows, refresh=False):
    records = []
    for row in rows:
        chain, address = row['chain'], row['address']
        url = None
        if source == 'walletexplorer' and chain == 'BTC':
            url = 'https://www.walletexplorer.com/api/1/address-lookup?address=' + quote(address)
        elif source == 'blockscout' and chain == 'ETH':
            url = 'https://eth.blockscout.com/api/v2/addresses/' + address
        elif source == 'etherscan_public' and chain == 'ETH':
            url = 'https://etherscan.io/address/' + address
        elif source == 'tronscan' and chain == 'TRX':
            url = 'https://apilist.tronscanapi.com/api/account?address=' + address
        if not url:
            continue
        body, meta = fetch(url, refresh=refresh)
        records.append(dict(row, source=source, url=url, **meta))
        try:
            obj = json.loads(body)
            note = {k: obj[k] for k in ('found', 'label', 'wallet_id', 'name', 'public_tags', 'addressTag', 'publicTag', 'addressTagLogo', 'accountType', 'greyTag') if k in obj}
        except (ValueError, TypeError):
            note = {'bytes': len(body)}
        print(source, address, meta['http_status'], json.dumps(note, ensure_ascii=False)[:450], flush=True)
    save_json(RAW / (source + '_checks.json.gz'), records)
    return source, len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['walletexplorer', 'blockscout', 'etherscan_public', 'tronscan'])
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    snapshot()
    rows = targets()
    save_json(RAW / 'targets.json.gz', rows)
    sources = [args.source] if args.source else ['walletexplorer', 'blockscout', 'etherscan_public', 'tronscan']
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures = [pool.submit(collect_source, source, rows, args.refresh) for source in sources]
        for future in concurrent.futures.as_completed(futures):
            print('complete', future.result(), flush=True)


if __name__ == '__main__':
    main()
