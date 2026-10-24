#!/usr/bin/env python3
"""Offline UTXO evidence audit, optional independent BTC checks, source report."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from fetch import ROOT, RAW, Client, FetchError, SYMBOLS, load_addresses, read_json, write_json, timeline_path, now, validate, rel, cache_snapshot


def finalize(rows):
    """Freeze early pilot cache refs and standardize source observation metadata."""
    refs = {}
    def immutable(ref):
        file, fragment = ref.split('#', 1)
        path = ROOT / file
        if not re.fullmatch('[0-9a-f]{64}\\.json\\.gz', path.name):
            return ref
        if file not in refs:
            envelope = read_json(path)
            digest = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode()).hexdigest()[:16]
            snapshot = path.with_name(path.name[:-8] + '-' + digest + '.json.gz')
            if not snapshot.exists():
                write_json(snapshot, envelope)
            refs[file] = rel(snapshot)
        return refs[file] + '#' + fragment
    for row in rows:
        path = timeline_path(row)
        if not path.exists():
            continue
        t = read_json(path)
        for tx in t['txs']:
            tx['raw_ref'] = immutable(tx['raw_ref'])
        if t['balance_now']:
            for balance in t['balance_now']:
                balance['raw_ref'] = immutable(balance['raw_ref'])
                envelope = read_json(ROOT / balance['raw_ref'].split('#')[0])
                balance['reported_at'] = envelope['fetched_at']
                balance['source'] = envelope.get('request', {}).get('url', t['source'])
            t['coverage']['to_time'] = t['balance_now'][0]['reported_at']
        t['coverage']['to_block'] = None
        if t['coverage']['complete']:
            t['coverage']['from_block'] = 0
        write_json(path, t)
    # Cache slots reference immutable snapshots; hard links save project disk.
    compacted = 0
    for path in RAW.glob('*/*/*.json.gz'):
        if not re.fullmatch('[0-9a-f]{64}\\.json\\.gz', path.name):
            continue
        envelope = read_json(path)
        digest = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode()).hexdigest()[:16]
        snapshot = path.with_name(path.name[:-8] + '-' + digest + '.json.gz')
        if snapshot.exists() and path.stat().st_ino != snapshot.stat().st_ino:
            cache_snapshot(snapshot, path)
            compacted += 1
    print('finalized timeline metadata; compacted cache slots', compacted, flush=True)


def cross_check(rows):
    candidates = []
    for row in rows:
        path = timeline_path(row)
        if row["chain"] == "btc" and path.exists():
            timeline = read_json(path)
            if timeline["coverage"]["complete"]:
                candidates.append((len(timeline['txs']), path))
    chosen = sorted(candidates, key=lambda item: -item[0])[:15]
    client = Client(1.1)
    previous_path = RAW / 'independent-validation.json.gz'
    previous = {r['address']: r for r in read_json(previous_path)['results']} if previous_path.exists() else {}
    results = []
    for _, path in chosen:
        t = read_json(path)
        address = t["address"]
        txs = [tx for tx in t["txs"] if tx.get("block")]
        value_in = sum((int(Decimal(tx['amount']) * 100_000_000) for tx in txs if tx["direction"] == "in"), 0)
        value_out = sum((int(Decimal(tx['amount']) * 100_000_000) for tx in txs if tx["direction"] == "out"), 0)
        fees = sum((int(Decimal(tx['fee']) * 100_000_000) for tx in txs), 0)
        old = previous.get(address)
        if old and old['matches'] and len(txs) == old['confirmed_txs'] and value_in == old['sum_in_sat'] and value_out == old['sum_out_sat'] and fees == old['allocated_fees_sat'] and t['balance_now'][0]['amount_sat'] == old['api_balance_sat']:
            results.append(dict(old, reused_unchanged_history=True))
            continue
        source_url = f"https://blockstream.info/api/address/{address}"
        try:
            data, raw_ref = client.get(source_url, fresh=True, retries=1)
        except FetchError:
            source_url = f"https://mempool.space/api/address/{address}"
            data, raw_ref = client.get(source_url, fresh=True)
        api = data["chain_stats"]
        expected_balance = api["funded_txo_sum"] - api["spent_txo_sum"]
        result = {"chain": "btc", "address": address, "timeline": f"data/timelines/btc/{address}.json.gz", "confirmed_txs": len(txs),
                  "sum_in_sat": value_in, "sum_out_sat": value_out, "allocated_fees_sat": fees,
                  "calculated_balance_sat": value_in-value_out-fees, "api_balance_sat": expected_balance,
                  "difference_sat": value_in-value_out-fees-expected_balance, "api_confirmed_txs": api["tx_count"],
                  "source_url": source_url, "raw_ref": raw_ref}
        result['checked_at'] = read_json(ROOT / raw_ref.split('#')[0])['fetched_at']
        result["matches"] = result["difference_sat"] == 0 and result["confirmed_txs"] == api["tx_count"]
        results.append(result)
        print(json.dumps(result), flush=True)
    write_json(RAW / "independent-validation.json.gz", {"fetched_at": now(), "script": "scripts/fetch/utxo/audit.py --cross-check",
               "selection": "15 largest complete BTC histories, including the largest three", "results": results, "network_calls": client.network_calls})


def report(rows, write_docs, input_path):
    validate(rows)
    validation = read_json(RAW / 'validation.json.gz')
    bootstrap = load_addresses(ROOT / 'data/bootstrap/fetch_utxo.csv')
    ledger_rows = load_addresses(input_path)
    bootstrap_set = {(r['chain'], r['address']) for r in bootstrap}
    ledger_set = {(r['chain'], r['address']) for r in ledger_rows}
    extra = Counter(r['chain'] for r in ledger_rows if (r['chain'], r['address']) not in bootstrap_set)
    checks = read_json(RAW / 'independent-validation.json.gz') if (RAW / 'independent-validation.json.gz').exists() else {"results": []}
    manifest = {"generated_at": now(), "input": str(input_path), "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "bootstrap": "data/bootstrap/fetch_utxo.csv", "bootstrap_addresses": len(bootstrap), "input_addresses": len(ledger_rows), 'audit_cohort_entries': len(rows),
                'bootstrap_only': [{'chain': c, 'address': a} for c,a in sorted(bootstrap_set-ledger_set)],
                "counts": validation["counts"], "addresses": [], "script": "scripts/fetch/utxo/audit.py"}
    for row in rows:
        path = timeline_path(row)
        if path.exists():
            t = read_json(path)
            manifest['addresses'].append({"chain": row['chain'], "address": row['address'], "timeline": rel(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "complete": t['coverage']['complete'],
                "tx_rows": len(t['txs']), "source_url": t['source'] if t['source'] and '://' in t['source'] else t.get('input_source_url'), "raw_ref": t['balance_now'][0]['raw_ref'] if t['balance_now'] else t.get('input_raw_ref'),
                "coverage": t['coverage']})
    write_json(RAW / 'coverage-manifest.json.gz', manifest)
    if not write_docs:
        return
    sources = {"btc": "https://btc1.trezor.io/api/v2 (Blockbook); https://blockstream.info/api and https://mempool.space/api (Esplora)",
               "ltc": "https://litecoinspace.org/api", "dash": "https://insight.dash.org/insight-api", "bsv": "https://api.whatsonchain.com/v1/bsv/main",
               "btg": "https://btgexplorer.com/api/v2", "doge": "https://api.blockcypher.com/v1/doge/main", "bch": "ssl://bch.imaginary.cash:50002",
               "zec": "No working keyless source found; saved probes", "xvg": "No working keyless source found; saved probes",
               "xmr": "Untrackable without a view key; https://www.getmonero.org/resources/moneropedia/stealthaddress.html"}
    counts = ["| Ticker | Bootstrap entries | Ledger entries | Audit entries | Complete histories | Coverage entries only | Confirmed address–transaction rows | Source / raw evidence |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    bc = Counter(r['chain'] for r in bootstrap)
    lc = Counter(r['chain'] for r in ledger_rows)
    bootstrap_manifest = read_json(RAW / 'bootstrap-manifest.json.gz')
    for chain, c in sorted(validation['counts'].items(), key=lambda i:(i[0] != 'btc', i[0])):
        counts.append(f"| {SYMBOLS[chain]} | {bc[chain]} | {lc[chain]} | {c['input_addresses']} | {c['complete']} | {c['input_addresses']-c['complete']} | {c['confirmed_address_transactions']} | {sources[chain]}; `data/raw/utxo/coverage-manifest.json.gz#counts.{chain}` |")
    lines = ["# UTXO sources and coverage", "", f"Generated {now()} by `scripts/fetch/utxo/audit.py --docs`. Counts are chain/address pairs; transaction rows can repeat a transaction across several listed addresses. No entity or monetary totals are inferred from these counts.", "",
             "## Address universe", "", f"Bootstrap: the `lists` branch of `0xB10C/ofac-sanctioned-digital-currency-addresses`, pinned to commit `{bootstrap_manifest['commit']}`. The list files are at the branch root, rather than a `lists/` directory. `data/bootstrap/fetch_utxo.csv` retains each pinned URL and raw reference. `data/raw/utxo/bootstrap-manifest.json.gz` records the commit/tree/list evidence.", "",
             f"The bootstrap contains {len(bootstrap)} output-based-chain entries: {sum(r['chain'] != 'xmr' for r in bootstrap)} transparent-UTXO ticker entries and {sum(r['chain'] == 'xmr' for r in bootstrap)} Monero entries. The OFAC-derived ledger file contains {len(ledger_rows)} relevant chain/address pairs, including {sum(extra.values())} additional entries ({', '.join(str(n)+' '+SYMBOLS[c] for c,n in sorted(extra.items()))}). The audit covers the union of both inputs: {len(rows)} entries. The fetcher accepts both CSV contracts, normalizes ticker/chain aliases (including XBT → btc), and preserves address spelling. Uppercase shared-ledger chain names map to lowercase timeline directories.", "",
             "The bootstrap XBT entry `TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq` is not a Bitcoin mainnet address. The finalized ledger resolves it to TRX and preserves OFAC's source-ticker mismatch. It remains a BTC coverage entry solely to account for every bootstrap input; no Bitcoin balance or history is asserted. An early explorer zero response was rejected after the chain correction. Mainnet Base58Check and BIP173/BIP350 checks now run before BTC API calls. This entry must not enter Bitcoin financial/activity denominators; its actual history belongs to the Tron fetcher.", "", *counts, "",
             "## Fetching and evidence", "", "```sh", ".venv/bin/python scripts/fetch/utxo/fetch.py --bootstrap", ".venv/bin/python scripts/fetch/utxo/fetch.py --addresses data/addresses.csv", ".venv/bin/python scripts/fetch/utxo/fetch.py --addresses data/addresses.csv --refresh", ".venv/bin/python scripts/fetch/utxo/fetch.py --addresses data/addresses.csv --skip-complete", ".venv/bin/python scripts/fetch/utxo/fetch.py --addresses data/addresses.csv --check", ".venv/bin/python scripts/fetch/utxo/audit.py --cross-check --docs", "```", "",
             "Python standard library only; no extra package dependency. Raw responses live under `data/raw/utxo/<host>/`, gzip-compressed and keyed by method/request. Every response used by a normalized timeline has an immutable snapshot; a second stable filename is the resumable cache. References such as `#response.transactions[3]` identify the JSON member and array index. Electrum references identify raw transaction hex; the saved prevout and block-header references support decoding. No API credentials are used. Source probes and error bodies are retained. No AWS parquet was downloaded.", "",
             "One 529-transaction BTC address (`bc1qw0pswznckx7s6tjmd2f5hrx4q6kc5nyrdxku50`) exceeded the 100 MiB Blockbook parser cap. Its full history was fetched through mempool.space instead and reconciled. The fetcher now streams oversized bodies into gzip sidecars with request metadata before using a smaller-page source, with a 512 MiB archive cap. The earlier rejected diagnostic body was not retained; the retry retained a diagnostic prefix explicitly marked incomplete in `data/raw/utxo/oversized-response-check.json.gz` and its linked metadata. No normalized timeline row depends on discarded or truncated diagnostic data.", "",
             "`--check` is offline. A normal completed rerun only checks head/balance metadata (Electrum and WhatsOnChain also need the compact transaction-id history as the source exposes no address transaction count). Cached transaction bodies are reused. `--refresh` uses a recent-block overlap for Blockbook/Esplora/BlockCypher, preserving older confirmed history. `--skip-complete` is for resuming an interrupted batch and deliberately skips its head checks. Confirmed balance and unconfirmed balance are separate. Checkpoints are left to analysis.", "",
             "## Working sources and rate limits", "",
             "- **BTC:** Blockbook `address?details=basic`, then `address?details=txs&pageSize=1000&page=N`; pages include full prevouts and outputs. Esplora `address`, then `address/txs/chain[/last_txid]`, 25 confirmed transactions per page, is the fallback and independent check. Initial 0.55-second spacing triggered Trezor HTTP 429; resumed production uses 1.3 seconds per host. The default is 1.1 seconds, and HTTP 429 adds at least 30 seconds of coordinated backoff. Blockstream's saved quota notice specifies 700 requests/hour/IP and 500,000 unauthenticated requests/month; after its quota response, the history fallback moved to mempool.space. These client settings are not a provider SLA. Failures never establish inactivity.",
             "- **LTC:** litecoinspace Esplora, 25 confirmed transactions per page. Default 1.1 seconds per host. All indexed confirmed history is fetched and balances reconciled. Trezor's LTC hosts returned HTTP 403 in this environment.",
             "- **BCH:** verified-TLS Electrum JSON-RPC at `bch.imaginary.cash:50002`. `blockchain.scripthash.get_history/get_balance`, `blockchain.transaction.get`, and `blockchain.block.header`. Raw transactions and all input prevouts are retained; transaction IDs are verified by double SHA-256. P2PKH/P2SH CashAddr and legacy encodings match by locking script. Client spacing 1.1 seconds per request. Public HTTP alternatives failed: Trezor HTTP 403, Blockchair HTTP 430 shared-IP quota block, loping.net bot challenge, imaginary.cash HTTPS timeout. The TCP/TLS Electrum service works independently of that HTTPS endpoint.",
             "- **BSV:** WhatsOnChain legacy address history/balance, then transaction bodies and previous transaction outputs. Client spacing 1.1 seconds per request. The returned confirmed history reconciles; the source is not independently cross-indexed.",
             "- **DASH:** Insight address summary/txid list and `/tx/<hash>`. Client spacing 1.1 seconds per request. Returned transaction-id list lengths match source counts. Larger future address lists require Insight pagination if their lengths differ; the fetcher marks that case incomplete.",
             "- **BTG:** btgexplorer Blockbook. Client spacing 1.1 seconds per request. The confirmed history reconciles. The nominal bitcoingold.org explorer and Trezor host failed DNS; btgpool.pro failed certificate verification, which was not disabled.",
             "- **DOGE:** BlockCypher `/addrs/<address>/balance` and `/full?limit=50`; truncated transaction input/output lists are expanded with `/txs/<hash>?limit=1000`. All expected inputs/outputs must be present. Default spacing 1.1 seconds per host; free API limits are provider-controlled and HTTP 429 is backed off. The collected histories reconcile.",
             "- **ZEC:** transparent addresses only are in scope. Trezor ZEC hosts returned HTTP 403, zcha.in returned HTTP 520, and alternate endpoints failed DNS/TLS, returned HTTP 403, or timed out. No working source found in the tested set; all four addresses have explicit coverage stubs. Shielded transfers cannot be attributed beyond transparent inputs/outputs.",
             "- **XVG:** tested explorer hosts fail DNS; verge-blockchain.info reports HTTP 503 database-reorg maintenance; Cryptoid reports HTTP 404 hosting expired. Its single address has an explicit coverage stub.", "",
             "- **XMR:** all Monero entries are retained as explicitly untrackable, including malformed source strings and a historical correction retained by the ledger. Public addresses do not reveal attributable stealth outputs, confidential amounts or true spend inputs; no view keys are available. This is a protocol privacy limitation, rather than an empty history. Balance fields remain unknown; per-entry ledger reasons are preserved. Source: https://www.getmonero.org/resources/moneropedia/stealthaddress.html (saved under `data/raw/utxo/www.getmonero.org/`).", "",
             "Source availability evidence: `data/raw/utxo/source-probes.json.gz`, `extra-probes.json.gz`, `probes/*.json.gz`, and `discovery/*.json.gz`. Availability is observed at fetch time; it is not a permanent statement about a chain.", "",
             "## UTXO amount and fee accounting", "",
             "Each transaction records the address's full input value, full output value, signed `net_value` (outputs minus inputs), input/output address lists, and individual input/output values in satoshis. `amount` is a nonnegative native-unit decimal. On a net debit it excludes the allocated fee; on a net credit it is the net credit. A pure self transfer has zero amount and a fee. `sum(in amount) - sum(out amount) - sum(fee)` therefore equals the sum of signed net values, and must equal the reported confirmed balance for complete histories.", "",
             "A multi-input transaction has no provable per-address fee payer. `tx_fee` is the full transaction fee; `fee` uses a documented accounting allocation: transaction fee × address input value / all input value, rounded down to a satoshi and capped at the address's net debit. This is a convention, not an ownership claim. Downstream work should use `net_value` for address balance changes and avoid summing full transaction fees across addresses.", "",
             "Coverage is native transparent value. BCH CashTokens/SLP and other colored-coin metadata are not parsed; the ERC-20/TRC-20/BEP-20 portions of the shared contract belong to account-chain fetchers. Nonstandard scripts can have no decoded address. No labels or controller identities are inferred.", "",
             "Downstream analysis must inspect `coverage.complete`, not only the ledger's route-based `trackable` flag. The initial ledger marks BTG untrackable because its provider had not been verified; this analysis verified btgexplorer and reconciled its full history. The ledger maintainer should reconcile that flag. Conversely, ZEC and XVG have listed routes but no usable data source in these probes. This analysis does not edit the shared ledger.", "",
             "## Validation", "", "`data/raw/utxo/validation.json.gz` covers every input address, required fields, raw-file existence, unique transaction hashes per address, transaction counts, and integer-satoshi reconciliation. `coverage-manifest.json.gz` records every timeline checksum, coverage, source and balance raw reference. `independent-validation.json.gz` checks the 15 largest complete BTC histories against Blockstream and includes the largest three.", "",
             "`scripts/fetch/utxo/checks.py` exercises a completed rerun and a refresh for each of the seven working source families. All 14 cases passed; default completed reruns fetched only head/balance metadata (and compact ID history where required), with unchanged transaction hashes. Exact requests and raw references are in `data/raw/utxo/refresh-checks.json.gz`.", "",
             "| BTC address | Confirmed transaction rows | In amount (sat) | Out amount (sat) | Allocated fees (sat) | API balance (sat) | Difference (sat) | Raw evidence |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in checks['results']:
        lines.append(f"| `{r['address']}` | {r['confirmed_txs']} | {r['sum_in_sat']} | {r['sum_out_sat']} | {r['allocated_fees_sat']} | {r['api_balance_sat']} | {r['difference_sat']} | `{r['raw_ref']}` |")
    lines.extend(["", "All amounts in the validation table are integer satoshis of BTC, not USD. Missing histories have no known balance; they are not entered as zero-balance observations.", "", "## Explicit incomplete histories", ""])
    gaps = [a for a in manifest['addresses'] if not a['complete']]
    if not gaps:
        lines.append("None.")
    for a in gaps:
        lines.append(f"- **{a['chain'].upper()} `{a['address']}`:** {' '.join(a['coverage']['notes'])} Timeline: `{a['timeline']}`. Raw evidence: `data/raw/utxo/coverage-manifest.json.gz#addresses` and the timeline's source probes.")
    lines.extend(["", "Any exchange-scale history that remains incomplete must not be described as having no outflow. Designation T−60d to T+400d and latest-90-day coverage must be independently established before publishing a window-specific finding. Fully reconciled whole histories include those windows through the API observation time; unavailable-source stubs cover none of them.", ""])
    (ROOT/'docs/sources/UTXO.md').write_text('\n'.join(lines))
    section = ["## fetch_utxo", "", f"Snapshot: {now()}. See [UTXO sources](sources/UTXO.md), `scripts/fetch/utxo/fetch.py`, `scripts/fetch/utxo/audit.py`, and `data/raw/utxo/coverage-manifest.json.gz`.", "", *counts, "",
               f"Independent balance checks: {len(checks['results'])} BTC addresses, including the three largest complete histories; {sum(not r['matches'] for r in checks['results'])} mismatches. Full per-address validation is in `data/raw/utxo/validation.json.gz`. Unavailable histories have unknown balances, not zero balances. No controller identities or compliance conclusions are inferred.", ""]
    for a in gaps:
        section.append(f"- {a['chain'].upper()} `{a['address']}`: {' '.join(a['coverage']['notes'])} Evidence: `{a['timeline']}`.")
    section.append("")
    target = ROOT/'docs/COVERAGE.md'
    content = target.read_text() if target.exists() else "# Coverage\n\n"
    # Own only this explicitly delimited section, preserving concurrent sections.
    start, end = '<!-- fetch_utxo:start -->', '<!-- fetch_utxo:end -->'
    block = start+'\n'+'\n'.join(section)+'\n'+end+'\n'
    if start in content and end in content:
        target.write_text(content[:content.index(start)] + block.rstrip('\n') + content[content.index(end)+len(end):])
    else:
        with target.open('a') as f:
            f.write(('\n' if target.exists() else '# Coverage\n\n') + block)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--addresses', type=Path, default=ROOT/'data/addresses.csv')
    p.add_argument('--cross-check', action='store_true')
    p.add_argument('--docs', action='store_true')
    p.add_argument('--finalize', action='store_true', help='Offline: freeze pilot refs, correct observation metadata, compact caches; run after fetches stop')
    args = p.parse_args()
    merged = {(r['chain'], r['address']): r for r in load_addresses(ROOT/'data/bootstrap/fetch_utxo.csv')}
    merged.update({(r['chain'], r['address']): r for r in load_addresses(args.addresses)})
    rows = sorted(merged.values(), key=lambda r:(r['chain'] != 'btc', r['chain'], r['address']))
    if args.finalize:
        finalize(rows)
    if args.cross_check:
        cross_check(rows)
    report(rows, args.docs, args.addresses)


if __name__ == '__main__':
    main()
