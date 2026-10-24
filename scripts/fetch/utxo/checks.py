#!/usr/bin/env python3
"""Practical completed-rerun and bounded-refresh checks using saved histories."""
import argparse
from types import SimpleNamespace

from fetch import Client, RAW, ROOT, load_addresses, timeline_path, read_json, write_json, fetch_one, now


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--offline', action='store_true', help='Only check Bitcoin input validation and mismatch coverage')
    options = p.parse_args()
    rows = load_addresses(ROOT / "data/addresses.csv")
    from electrum import bitcoin_address_error
    assert bitcoin_address_error('1BpEi6DfDAUFd7GtittLSdBeYJvcoaVggu') is None
    assert bitcoin_address_error('1BpEi6DfDAUFd7GtittLSdBeYJvcoaVggv') is not None
    assert bitcoin_address_error('TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq') is not None
    invalid = []
    for row in load_addresses(ROOT / 'data/bootstrap/fetch_utxo.csv'):
        if row['chain'] == 'btc' and bitcoin_address_error(row['address']):
            t = read_json(timeline_path(row))
            assert not t['coverage']['complete'] and not t['balance_now'] and not t['txs']
            invalid.append({'chain': 'btc', 'address': row['address'], 'reason': bitcoin_address_error(row['address']),
                            'resolution': t.get('chain_resolution'), 'raw_ref': row.get('raw_ref')})
    valid_count = sum(r['chain'] == 'btc' and bitcoin_address_error(r['address']) is None for r in rows)
    write_json(RAW / 'input-validation-check.json.gz', {'checked_at': now(), 'script': 'scripts/fetch/utxo/checks.py --offline',
               'valid_ledger_btc_addresses': valid_count, 'invalid_bootstrap_entries': invalid, 'passed': True})
    print('Bitcoin input validation passed; valid ledger addresses', valid_count, 'bootstrap mismatch entries', len(invalid), flush=True)
    if options.offline:
        return
    selected = []
    for chain in ["btc", "ltc", "bch", "bsv", "dash", "btg", "doge"]:
        for row in rows:
            path = timeline_path(row)
            if row["chain"] == chain and path.exists() and read_json(path)["coverage"]["complete"]:
                selected.append(row)
                break
    c = Client(1.3)
    results = []
    for mode in ["completed_rerun", "refresh"]:
        for row in selected:
            old = read_json(timeline_path(row))
            start = c.network_calls
            first = len(c.request_log)
            response = fetch_one(c, row, SimpleNamespace(refresh=mode == "refresh", max_pages=0, page_size=1000))
            new = read_json(timeline_path(row))
            requests = c.request_log[first:]
            # The sample has no new source activity. Default reruns must request
            # no transaction bodies, only head/balance or compact ID history.
            if mode in ('completed_rerun', 'refresh'):
                only_heads = all(("/balance" in r["url"] or "details=basic" in r["url"] or "/history" in r["url"]
                                  or ("/address/" in r["url"] and "/txs" not in r["url"])
                                  or ("/addr/" in r["url"] and "/tx/" not in r["url"])
                                  or r.get("method") in ("blockchain.scripthash.get_balance", "blockchain.scripthash.get_history")) for r in requests)
            else:
                only_heads = None
            unchanged = [t['hash'] for t in old['txs']] == [t['hash'] for t in new['txs']]
            ok = new['coverage']['complete'] and unchanged and (only_heads is not False)
            result = {"mode": mode, "chain": row['chain'], "address": row['address'], "result": response,
                      "network_calls": c.network_calls-start, "requests": requests, "tx_hashes_unchanged": unchanged,
                      "completed_rerun_only_heads": only_heads, "passed": ok,
                      "raw_ref": new['balance_now'][0]['raw_ref'] if new['balance_now'] else None}
            results.append(result)
            print(mode, row['chain'], 'calls', result['network_calls'], 'passed', ok, flush=True)
    write_json(RAW / "refresh-checks.json.gz", {"fetched_at": now(), "script": "scripts/fetch/utxo/checks.py", "results": results})
    if not all(r['passed'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
