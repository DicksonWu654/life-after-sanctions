"""Build the owned source note and append this process’s coverage section.

Run only after validate.py has finished. Concurrent processes' coverage text is retained.
"""
import argparse
import json
import hashlib
from collections import Counter
from common import ROOT,addresses,load,now,timeline_path,save,utc

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--addresses',default='data/bootstrap/fetch_tron.csv')
    p.add_argument('--append-coverage',action='store_true')
    p.add_argument('--in-progress',action='store_true')
    args=p.parse_args()
    validation=load(ROOT/'data/raw/tron/validation.json.gz')
    if not args.in_progress:
        if validation['missing_timelines'] or validation['contract_errors'] or validation.get('protected_window_errors'):
            raise SystemExit('Final report requires zero missing files, contract errors and protected-window gaps')
        for value,digest in validation.get('input_sha256',{}).items():
            if hashlib.sha256((ROOT/value).read_bytes()).hexdigest()!=digest:
                raise SystemExit('Address input changed after validation; validate again: '+value)
    bootstrap=load(ROOT/'data/raw/tron/bootstrap/manifest.json.gz')
    inputs=validation.get('address_inputs',[args.addresses])
    fetch_input=validation.get('input',args.addresses)
    validate_command='.venv/bin/python scripts/fetch/tron/validate.py --addresses '+fetch_input
    for value in inputs:
        if value!=fetch_input:validate_command+=' --additional-addresses '+value
    inputs_text=', '.join('`'+value+'`' for value in inputs)
    union={}
    for value in inputs:
        for row in addresses(value):union[(row['chain'],row['address'])]=row
    rows=[r for r in union.values() if r['chain'] in ('trx','sol','xrp','bnb','xmr','unknown')];timelines=[]
    primary_rows=[r for r in addresses(ROOT/'data/addresses.csv') if r['chain'] in ('trx','sol','xrp','bnb','xmr','unknown')] if (ROOT/'data/addresses.csv').exists() else []
    primary_counts=dict(Counter(r['chain'] for r in primary_rows))
    bootstrap_keys={(r['chain'],r['address']) for r in addresses(ROOT/'data/bootstrap/fetch_tron.csv')}
    for row in rows:
        path=timeline_path(row['chain'],row['address'])
        if path.exists():timelines.append(load(path))
    statuses=Counter();rpc_rates=Counter();examples={}
    for source in ('tron','other'):
        for path in (ROOT/'data/raw'/source).rglob('*.json.gz'):
            if path.name in ('manifest.json.gz','validation.json.gz'):continue
            obj=load(path)
            if 'http_status' not in obj:continue
            code=obj['http_status']
            if code>=400 or code==0:
                statuses[(source,code)]+=1;examples.setdefault((source,code),str(path.relative_to(ROOT)))
            response=obj.get('response')
            result=response.get('result') if isinstance(response,dict) else None
            if isinstance(result,dict) and result.get('error') in ('tooBusy','slowDown'):
                rpc_rates[result['error']]+=1
    stats={'generated_at':now(),'bootstrap_commit':bootstrap['commit'],'http_status_counts':[
        {'source':s,'status':code,'responses':count,'example_raw_ref':examples[(s,code)]} for (s,code),count in sorted(statuses.items())],
        'rpc_rate_error_counts':dict(rpc_rates),'timeline_count':len(timelines),
        'counts_by_chain':dict(Counter(t['chain'] for t in timelines)),
        'usdt_balanceof_addresses':sum(any(b['asset']=='TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t' and 'balanceOf' in b['source'] for b in t['balance_now']) for t in timelines if t['chain']=='trx'),
        'tron_labels_responses':sum(bool(t.get('labels_raw_ref')) for t in timelines if t['chain']=='trx'),
        'tron_partial_with_complete_protected_windows':sum(not t['coverage']['complete'] and t['coverage'].get('priority_windows_complete',False) for t in timelines if t['chain']=='trx')}
    stats['receipt_resolved_transfer_signatures']=sum(len(t.get('token_resolution',{})) for t in timelines if t['chain']=='trx')
    stats['unresolved_events']=sum(len(t.get('unresolved_events',[])) for t in timelines if t['chain']=='trx')
    stats['tronscan_transfer_pages']=len(list((ROOT/'data/raw/tron/tronscan_trc20').glob('*.json.gz')))
    stats['tronscan_normalized_event_rows']=sum(e.get('indexer')=='TronScan' for t in timelines if t['chain']=='trx' for e in t['txs'])
    stats['receipt_fee_corrections']=[{'address':t['address'],'hash':e['hash'],'indexed_fee_sun':e['indexed_fee_sun'],
        'corrected_fee_trx':e['fee'],'raw_ref':e['fee_raw_ref']} for t in timelines if t['chain']=='trx'
        for e in t['txs'] if e.get('fee_raw_ref') and int(e.get('indexed_fee_sun','0'))!=int(t.get('fee_resolution',{}).get(e['hash'],{}).get('fee_sun',0))]
    stats['primary_counts']=primary_counts
    stats['primary_only_addresses']=[{'chain':r['chain'],'address':r['address'],'raw_ref':r.get('raw_ref'),
        'source_url':r.get('source_url')} for r in primary_rows if (r['chain'],r['address']) not in bootstrap_keys]
    save(ROOT/'data/raw/tron/source-summary.json.gz',stats)
    ref='data/raw/tron/validation.json.gz'
    lines=['# Tron, XRP, Solana, BNB Beacon and untrackable-chain source record','',f'Generated {stats["generated_at"]} by `scripts/fetch/tron/report.py`. Research data, not legal or compliance advice.','',
        '## Scope and provenance','',f'Bootstrap: 0xB10C public `lists` branch, pinned commit `{bootstrap["commit"]}`. The branch contains `sanctioned_addresses_<TICKER>.txt` at its root. Only data files were retrieved; upstream code was not run. This is a bootstrap extraction and must be reconciled to the authoritative OFAC ledger by its owner.',
        '',f'Inputs: {inputs_text}. Bootstrap request/commit evidence: `data/raw/tron/bootstrap/manifest.json.gz`. List tickers found: {", ".join(bootstrap["tickers_found"])}. The current primary ledger contains these distinct address counts in this process’s scope: `{primary_counts}`. Primary-only addresses and their OFAC provenance are recorded in `data/raw/tron/source-summary.json.gz`; they include Monero, BNB Beacon and an additional Tron record absent from the pinned bootstrap. Seven Bitcoin-format USDT bootstrap entries are retained as token-network-unresolved; the primary ledger assigns their address format to BTC, which does not identify the USDT token network.','',
        '| Chain | Address timeline files | Paged histories complete | Normalized event rows | raw_ref |',
        '|---|---:|---:|---:|---|']
    if args.in_progress:lines.insert(2,'**Collection is still running. These are interim saved-data counts; final validation and coverage reconciliation are pending.**\n')
    for chain,count in sorted(validation['counts_by_chain'].items()):
        lines.append(f'| {chain} | {count} | {validation["complete_by_chain"].get(chain,0)} | {validation["events_by_chain"].get(chain,0)} | `{ref}` |')
    lines+=['',f'{stats["usdt_balanceof_addresses"]} Tron addresses have a direct latest-state USDT `balanceOf(address)` result; {stats["tron_labels_responses"]} have a saved TronScan account/label response. Evidence: `data/raw/tron/source-summary.json.gz`. Rows are asset events, including fee-only rows, and must not be described as distinct transactions.','',
        '## Rebuild, resume and refresh','', 'All scripts use the existing uv project venv and the Python standard library; no extra package or key is needed. From the repository root:','',
        '```sh','.venv/bin/python scripts/fetch/tron/bootstrap.py',
        '.venv/bin/python scripts/fetch/tron/fetch.py --addresses '+fetch_input,
        '.venv/bin/python scripts/fetch/other/fetch.py --addresses '+fetch_input,
        '.venv/bin/python scripts/fetch/other/fetch.py --addresses data/bootstrap/fetch_tron.csv --chain unknown',
        '.venv/bin/python scripts/fetch/other/reconcile_xrp.py',
        '.venv/bin/python scripts/fetch/other/reparse_sol.py',
        '.venv/bin/python scripts/fetch/tron/windows.py --addresses '+fetch_input+' --ledger data/ledger.csv',
        '# If TronGrid token paging is throttled, use fallback_tokens.py --address ADDRESS; then rerun windows.py.',
        '.venv/bin/python scripts/fetch/tron/revalidate_tails.py --include-partial --addresses '+fetch_input,
        '.venv/bin/python scripts/fetch/tron/reparse.py --addresses '+fetch_input,
        validate_command,
        '.venv/bin/python scripts/fetch/tron/report.py --addresses '+fetch_input, '```','',
        'The same fetchers accept the bootstrap CSV and the primary data/addresses.csv without format changes. Add `--refresh` to append activity after the saved history boundary; timestamp overlap is intentional and event IDs deduplicate it. A completed rerun checks head/balances but skips completed history pages. For partial histories, `--refresh` starts at the newest proven boundary, including protected-window evidence, and retains older gaps for an ordinary resume without `--refresh`. Interrupted incremental batches retain their range proofs. Use `complete_gaps.py --address ADDRESS --max-pages 0` to merge existing prefix/protected proofs into parent coverage; a positive page budget fetches the remaining older gaps. Raw responses are saved per request; large normalized timelines checkpoint in batches (up to 25 pages), so an interrupted batch is replayed from cache. `--max-pages` bounds each invocation; rerun to continue. Address writer locks and unique temporary snapshot files prevent overlapping writers. Run `reparse.py` only after all Tron fetches have stopped.','',
        '## Source behavior and rate limits','',
        '- TronGrid: `/v1/accounts/{address}/transactions`, `/transactions/trc20`, and `/internal-transactions`, with confirmed ascending 200-row pages. Fingerprints are followed; after five full pages the last timestamp is requeried inclusively in a new min/max window. Failed/expired cursors split the time interval. Single-millisecond overflows remain explicit gaps.',
        '- History cutoffs use `/walletsolidity/getnowblock` so the cutoff is confirmed, matching only_confirmed=true. Earlier latest-head cutoffs have their last two minutes requeried after confirmation; proof is in tail_revalidation and data/raw/tron/tail-revalidation-summary.json.gz. Latest account/USDT balances remain separate observations from the latest-state endpoints.',
        '- TRX state: `/wallet/getaccount`; an omitted balance field is recorded as zero under the API default. TRC-10 metadata and reported token balances also come from TronScan. USDT always gets a direct `/wallet/triggerconstantcontract` query, including frozen or unactivated accounts. It is a read-only constant call and broadcasts no transaction.',
        '- TronScan `/api/account` works keylessly and its full account response, including any public tags, is under `data/raw/tron/labels/`. `/api/accountv2` returned 401. Native `/api/transaction` and `/api/token_trc20/transfers` probes are saved under `data/raw/tron/fallback/`. Requests asking for 200 rows returned only 50, and a native type=31 filter returned 401; native sort=timestamp still returned descending rows. Native collection remains on TronGrid. The token fallback validates descending order, address filters, confirmed status and timestamp bounds, follows 50-row offset pages, then restarts inclusively at a timestamp boundary before the 10,000-row explorer cap. Actual pages are saved under data/raw/tron/tronscan_trc20/. Native and fallback token event IDs agree and deduplicate overlapping evidence. Labels remain leads, not controller attribution.',
        '- Saved HTTP 429 bodies report allowed_rps(1), and some later responses report 3, with one- to five-second suspensions. Early polling used 0.5/0.7-second gaps plus response latency and 4/8/16-second backoff. The client enforces a conservative shared 1.2-second minimum between TronGrid request starts across partitions. HTTP 429 responses now impose a shared 6/12/24-second cooldown as well as per-request retry backoff, avoiding competing retries during provider suspensions. Advisory throttle/cooldown files under data/raw/tron/rate-limit are runtime state, not API evidence. HTTP 400/404 probes are distinguishable from collection failures in the saved request URL.',
        '- XRP: `account_tx` (200 rows, forward, validated ledger bound), `account_info`, `account_lines`. Public servers: xrplcluster.com and Ripple s1/s2. RPC tooBusy/slowDown responses specify 2,000 units/10 seconds and 10,000 units/60 seconds. The fetcher now respects the stated retry delay and pins the paging server. Five cross-server cursor boundary gaps in the initial pass were repaired by ledger ranges and verified by AccountRoot continuity. Evidence: `data/raw/other/xrp/continuity-audit.json.gz`.',
        '- Solana: public mainnet-beta RPC, with publicnode/drpc fallbacks; finalized signatures (1,000 rows), JSON-parsed transactions, wallet SOL balance, classic Token and Token-2022 accounts. Raw responses include token-account histories that do not mention the wallet owner. RPC polling used 0.7 seconds plus latency.', '',
        '- BNB Beacon: legacy dex account state returns five BEP-2/native balances, while its transaction/head APIs return 500/502. The public explorer frontend identifies /api/v1/txs with address, startTime/endTime and page/rows (maximum 100). The working fallback reports 9,091,625 address history records; only the latest 200 and full designation/latest-90-day windows are fetched. Those windows are after the documented 2024-12-03 shutdown and return explicit zero-record responses. The remaining older history is an explicit huge-address gap. Raw evidence is under data/raw/other/bnb/.', '',
        '| Source | HTTP status | Saved responses | Example raw_ref |','|---|---:|---:|---|']
    for row in stats['http_status_counts']:
        lines.append(f'| {row["source"]} | {row["status"]} | {row["responses"]} | `{row["example_raw_ref"]}` |')
    lines+=['',f'Application-level XRP rate errors saved: `{dict(rpc_rates)}`. Evidence: `data/raw/tron/source-summary.json.gz`. Counts describe this fetch run, not a guaranteed provider quota.','',
        '## Validation','',f'`validate.py` checked {validation["timeline_count"]} timeline files and every transfer/balance raw-reference pointer. Missing timeline files: {len(validation["missing_timelines"])}; addresses with contract/provenance errors: {len(validation["contract_errors"])}; addresses with protected-window gaps: {len(validation.get("protected_window_errors",[]))}. Protected coverage is checked by the union of saved millisecond ranges, independently of completion flags. The selected reconciliation sample contains {validation["sample_address_count"]} addresses, including the three largest normalized timelines. Across all reported asset balances, {validation["balance_matches"]} of {validation["balance_checks"]} checks match within one base unit. Full exact differences, raw refs and cause/limit notes are in `{ref}`; successful paging alone is not a balance proof.','',
        '| Sample address | Chain | Event rows | raw_ref |','|---|---|---:|---|']
    samples={(r['chain'],r['address']) for r in validation['sample_reconciliations']}
    for t in sorted(timelines,key=lambda t:(-len(t['txs']),t['address'])):
        if (t['chain'],t['address']) in samples:
            lines.append(f'| `{t["address"]}` | {t["chain"]} | {len(t["txs"])} | `{timeline_path(t["chain"],t["address"]).relative_to(ROOT)}` |')
    incremental=ROOT/'data/raw/tron/incremental-validation.json.gz'
    if incremental.exists():
        inc=load(incremental)
        calls=[r['network_calls'] for r in inc['runs']]
        lines+=['',f'Two consecutive incremental refreshes and a completed default rerun succeeded on `{inc["address"]}`. Network calls were {calls}; the completed default rerun made {inc["completed_rerun_history_requests"]} history requests. Proof: `data/raw/tron/incremental-validation.json.gz`, its referenced API responses and three run logs.']
    other_incremental=ROOT/'data/raw/other/incremental-validation.json.gz'
    if other_incremental.exists():
        inc=load(other_incremental)
        lines+=['',f'XRP and all four Solana wallets passed two consecutive refreshes. A completed default rerun across the other primary-ledger addresses made {inc["completed_rerun_history_requests"]} history requests (head/balance checks only). Proof and refresh logs: `data/raw/other/incremental-validation.json.gz`. Solana refreshes force a fresh first signature page so cached empty results cannot hide later activity. The post-refresh XRP continuity audit is `data/raw/other/xrp/continuity-audit-final.json.gz`.']
    lines+=['',f'Empty indexer token metadata was resolved from receipt logs for {stats["receipt_resolved_transfer_signatures"]} transfer signatures. Unresolved event records: {stats["unresolved_events"]}. Evidence: timeline token_resolution/unresolved_events and `data/raw/tron/source-summary.json.gz`.']
    lines+=['',f'TronScan token fallback: {stats["tronscan_transfer_pages"]} saved response pages; {stats["tronscan_normalized_event_rows"]} normalized event rows currently use that indexer’s evidence. Evidence: `data/raw/tron/source-summary.json.gz`, `scripts/fetch/tron/fallback_tokens.py`, and data/raw/tron/tronscan_trc20/.']
    lines+=['',f'Node receipts corrected {len(stats["receipt_fee_corrections"])} originator fees that the history indexer reported as zero. The audited events retain indexed_fee_sun and fee_raw_ref; `scripts/fetch/tron/audit_fees.py` and `data/raw/tron/fee-audits/` reproduce these corrections. Other zero-fee indexer rows have not all been independently receipt-audited.']
    mismatch_counts=Counter(r['cause_or_limit'] for r in validation['reconciliations'] if not r['within_one_base_unit'])
    lines+=['','Mismatch categories (counts are address/asset checks):','']
    for reason,count in sorted(mismatch_counts.items()):lines.append(f'- {count}: {reason}. Evidence: `{ref}`.')
    lines+=['','## Coverage limits','',
        '- Tron coverage.complete means that confirmed native, internal and TRC-20 paging exhausted for the saved snapshot. TronGrid token/internal records omit block numbers; native transaction/receipt evidence supplies a block when available, with block_raw_ref. TronScan token rows provide their own block; remaining block fields stay null. Token indexes omit log indexes, so identical same-transaction logs at a page boundary can have unresolved multiplicity. These data should not support a claim of zero activity outside the checked range.',
        '- Native staking/unfreezing/reward state changes are retained in raw contract records but not interpreted as ordinary payments. TRC-10 events retain raw quantities; decimals are known only when reported token metadata exists. Transfer logs for rebasing/spam tokens need not reconcile with balance. Tether issuer burns can change USDT balance without Transfer; a discrepancy is not by itself proof of a burn.',
        '- Solana parsed System/SPL transfers are individual rows with is_transfer=true. Network fees and residual balance adjustments are explicit is_transfer=false rows; these may include rent/refunds, mint/burn, ownership changes or unparsed instructions and must not be described as ordinary payments. Old SPL owner omissions are resolved only from chronological explicit initialization/metadata/authority-change evidence, with owner_resolution_raw_refs. Closed token accounts absent from wallet history still prevent a full token-history claim. coverage.complete stays false even when every known signature is parsed. Mint symbols are null rather than guessed.',
        '- Monero is not address-trackable without private view keys; no balance or flow is inferred. Bitcoin-format USDT entries have no asserted token network or token history. Every such bootstrap address has an explicit timeline/coverage record.',
        '- BNB Beacon legacy state is not evidence of current spendability or recovery-contract holdings on BSC. Full older history and multi-send detail remain incomplete; no ownership label or legal conclusion is inferred from the address activity.',
        '- Latest balance observations occur at each request time, not a single atomic chain snapshot. `balance_now[].as_of` and raw request timestamps are authoritative. No designation/checkpoint balances are computed by this collector. The designation-window helper needs official dates in the primary ledger; missing dates are recorded rather than inferred.', '',
        'The per-address residual windows and unsupported-address list are in this process’s section of `docs/COVERAGE.md`.']
    (ROOT/'docs/sources/TRON.md').write_text('\n'.join(lines)+'\n')
    if args.append_coverage:
        if args.in_progress:raise SystemExit('Refusing to append interim counts as final coverage')
        section=['','## fetch_tron — Tron and other account/privacy chains', '',
            f'Final local fetch/validation snapshot: {stats["generated_at"]}. Inputs {inputs_text}; bootstrap commit `{bootstrap["commit"]}`. Source/method details: `docs/sources/TRON.md`; machine-readable validation: `{ref}`.','',
            'Counts are distinct address timeline files per chain, not entities or designation actions.','']
        for chain,count in sorted(validation['counts_by_chain'].items()):
            section.append(f'- {chain}: {count} address timelines; {validation["complete_by_chain"].get(chain,0)} have completed paging; {validation["events_by_chain"].get(chain,0)} normalized event rows. Evidence: `{ref}`.')
        section+=['','Tron: confirmed direct native transactions, independent internal transfers and all TRC-20 Transfer pages are queried. Per-asset current balances include direct USDT balanceOf even when frozen. TRC-10 decimal, staking/reward, missing block/log-index and issuer-burn limitations are detailed in the source note. Completed paging is separate from asset reconciliation.','',
            'Residual or unsupported histories (each address remains in the dataset):','',
            '| Chain | Address | Gap/limit | raw_ref |','|---|---|---|---|']
        for t in sorted(timelines,key=lambda t:(t['chain'],t['address'])):
            if t['coverage']['complete']:continue
            ch=t['chain'];notes=[]
            if ch=='trx':
                exact=t['coverage'].get('missing_time_windows',{})
                for name,s in t.get('fetch_state',{}).items():
                    if name in exact:
                        if exact[name]:notes.append(name+': '+', '.join(utc(w['from_ms'])+' through '+utc(w['to_ms']) for w in exact[name]))
                    elif s['pending']:notes.append(f'{name}: {len(s["pending"])} pending intervals, exact millisecond bounds in fetch_state')
                    if s.get('gaps'):notes.append(f'{name}: {len(s["gaps"])} unsplittable intervals')
                    if s.get('error'):notes.append(name+': provider error (saved raw_ref in fetch_state)')
                if t.get('unresolved_events'):notes.append(f'{len(t["unresolved_events"])} unresolved metadata events; exact hashes/raw refs in unresolved_events')
                if 'priority_windows' in t:notes.append('priority windows complete='+str(t['coverage'].get('priority_windows_complete'))+'; official dates available='+str(t['coverage'].get('priority_window_dates_available')))
            elif ch=='sol':notes.append('Known wallet/token-account signatures fetched; closed-account discovery remains incomplete. Parsed transfers and non-payment balance adjustments are separate')
            elif ch=='xmr':notes.append('Untrackable publicly: private view keys required; no balance/flow inference')
            elif ch=='unknown':notes.append('Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched')
            elif ch=='bnb':notes.append(f'Explorer reports {t.get("reported_history_records")} history records; latest 200 sampled, full designation/latest-90-day windows complete={t["coverage"].get("priority_windows_complete")}; older missing block range in coverage.missing_intervals. Legacy balances are not BSC recovery balances')
            else:notes.extend(t['coverage']['notes'])
            if not notes:notes.append('See per-address coverage notes')
            section.append(f'| {ch} | `{t["address"]}` | {"; ".join(notes).replace("|","/")} | `{timeline_path(ch,t["address"]).relative_to(ROOT)}` |')
        section+=['','No outflow found means only within the saved data checked. The fetcher never infers controller identities or legal violations. Solana wallet SOL balances and XRP AccountRoot balances are validated independently from completeness claims.','']
        dest=ROOT/'docs/COVERAGE.md'
        new_file=not dest.exists()
        existing=dest.read_text() if dest.exists() else '# Coverage\n'
        if '## fetch_tron —' in existing:
            raise SystemExit('Coverage section already exists; source note was updated, but append refused to avoid duplicate sections')
        with dest.open('a') as f:
            if new_file or not existing: f.write('# Coverage\n')
            f.write('\n'.join(section))
    print(json.dumps(stats))

if __name__=='__main__':main()
