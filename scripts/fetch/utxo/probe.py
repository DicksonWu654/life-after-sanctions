#!/usr/bin/env python3
"""Save keyless explorer availability probes using the fetcher's raw recorder."""
import argparse
import concurrent.futures
import json
from fetch import Client, FetchError, load_addresses, ROOT, RAW, write_json, now


def candidates(rows):
    addresses = {}
    for row in rows:
        addresses.setdefault(row["chain"], row["address"])
    urls = []
    for chain in ("ltc", "bch", "zec", "doge"):
        if chain in addresses:
            for n in (1, 2, 3):
                urls.append((chain, f"https://{chain}{n}.trezor.io/api/v2/address/{addresses[chain]}?details=txs&pageSize=1000"))
    for chain in ("xvg", "btg", "doge", "zec"):
        if chain in addresses:
            urls.append((chain, f"https://chainz.cryptoid.info/{chain}/api.dws?q=multiaddr&active={addresses[chain]}&n=100"))
    for base in ("https://bch.loping.net/api", "https://bch.imaginary.cash/api"):
        urls.append(("bch", f"{base}/address/{addresses['bch']}"))
    for base in ("https://explorer.btgpool.pro/api/v2", "https://btgexplorer.com/api/v2"):
        urls.append(("btg", f"{base}/address/{addresses['btg']}?details=txs&pageSize=1000"))
    for base in ("https://explorer.verge-blockchain.com/api", "https://verge-blockchain.info/api", "https://explorer.vergecurrency.com/api"):
        urls.append(("xvg", f"{base}/getaddress?address={addresses['xvg']}"))
    for base in ("https://zecblockexplorer.com/api", "https://explorer.zec.rocks/api"):
        urls.append(("zec", f"{base}/addr/{addresses['zec']}"))
    return urls


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--addresses", type=__import__('pathlib').Path, default=ROOT / 'data/addresses.csv')
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--url", action="append", help="CHAIN=URL; overrides default candidates")
    p.add_argument("--output", default="source-probes")
    args = p.parse_args()
    client = Client(interval=1)
    def probe(item):
        chain, url = item
        try:
            data, ref = client.get(url, timeout=12, retries=1, fresh=args.fresh)
            status, summary = 200, str(data)[:200]
        except FetchError as e:
            ref, status, summary = e.raw_ref, None, str(e)
        result = {"chain": chain, "source_url": url, "raw_ref": ref, "status": status, "summary": summary}
        print(json.dumps(result), flush=True)
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        targets = [tuple(u.split('=', 1)) for u in args.url] if args.url else candidates(load_addresses(args.addresses))
        results = list(pool.map(probe, targets))
    write_json(RAW / (args.output + '.json.gz'), {"fetched_at": now(), "script": "scripts/fetch/utxo/probe.py", "probes": results})


if __name__ == '__main__':
    main()
