# Tron, XRP, Solana, BNB Beacon and untrackable-chain source record

Generated 2026-10-23T13:27:44.450657Z by `scripts/fetch/tron/report.py`. Research data, not legal or compliance advice.

## Scope and provenance

Bootstrap: 0xB10C public `lists` branch, pinned commit `6ae2472c439b9bb2788f8df662052ae31854aa97`. The branch contains `sanctioned_addresses_<TICKER>.txt` at its root. Only data files were retrieved; upstream code was not run. This is a bootstrap extraction and must be reconciled to the authoritative OFAC ledger against official sources.

Inputs: `data/addresses.csv`, `data/bootstrap/fetch_tron.csv`. Bootstrap request/commit evidence: `data/raw/tron/bootstrap/manifest.json.gz`. List tickers found: ARB, BCH, BSC, BSV, BTG, DASH, ETC, ETH, LTC, SOL, TRX, USDC, USDT, XBT, XMR, XRP, XVG, ZEC. The current primary ledger contains these distinct address counts for these chains: `{'bnb': 1, 'sol': 4, 'trx': 341, 'xmr': 12, 'xrp': 1}`. Primary-only addresses and their OFAC provenance are recorded in `data/raw/tron/source-summary.json.gz`; they include Monero, BNB Beacon and an additional Tron record absent from the pinned bootstrap. Seven Bitcoin-format USDT bootstrap entries are retained as token-network-unresolved; the primary ledger assigns their address format to BTC, which does not identify the USDT token network.

| Chain | Address timeline files | Paged histories complete | Normalized event rows | raw_ref |
|---|---:|---:|---:|---|
| bnb | 1 | 0 | 225 | `data/raw/tron/validation.json.gz` |
| sol | 4 | 0 | 131 | `data/raw/tron/validation.json.gz` |
| trx | 341 | 340 | 1450010 | `data/raw/tron/validation.json.gz` |
| unknown | 7 | 0 | 0 | `data/raw/tron/validation.json.gz` |
| xmr | 12 | 0 | 0 | `data/raw/tron/validation.json.gz` |
| xrp | 1 | 1 | 7608 | `data/raw/tron/validation.json.gz` |

341 Tron addresses have a direct latest-state USDT `balanceOf(address)` result; 341 have a saved TronScan account/label response. Evidence: `data/raw/tron/source-summary.json.gz`. Rows are asset events, including fee-only rows, and must not be described as distinct transactions.

## Rebuild, resume and refresh

All scripts use the existing uv project venv and the Python standard library; no extra package or key is needed. From the repository root:

```sh
.venv/bin/python scripts/fetch/tron/bootstrap.py
.venv/bin/python scripts/fetch/tron/fetch.py --addresses data/addresses.csv
.venv/bin/python scripts/fetch/other/fetch.py --addresses data/addresses.csv
.venv/bin/python scripts/fetch/other/fetch.py --addresses data/bootstrap/fetch_tron.csv --chain unknown
.venv/bin/python scripts/fetch/other/reconcile_xrp.py
.venv/bin/python scripts/fetch/other/reparse_sol.py
.venv/bin/python scripts/fetch/tron/windows.py --addresses data/addresses.csv --ledger data/ledger.csv
# If TronGrid token paging is throttled, use fallback_tokens.py --address ADDRESS; then rerun windows.py.
.venv/bin/python scripts/fetch/tron/revalidate_tails.py --include-partial --addresses data/addresses.csv
.venv/bin/python scripts/fetch/tron/reparse.py --addresses data/addresses.csv
.venv/bin/python scripts/fetch/tron/validate.py --addresses data/addresses.csv --additional-addresses data/bootstrap/fetch_tron.csv
.venv/bin/python scripts/fetch/tron/report.py --addresses data/addresses.csv
```

The same fetchers accept the bootstrap CSV and the primary data/addresses.csv without format changes. Add `--refresh` to append activity after the saved history boundary; timestamp overlap is intentional and event IDs deduplicate it. A completed rerun checks head/balances but skips completed history pages. For partial histories, `--refresh` starts at the newest proven boundary, including protected-window evidence, and retains older gaps for an ordinary resume without `--refresh`. Interrupted incremental batches retain their range proofs. Use `complete_gaps.py --address ADDRESS --max-pages 0` to merge existing prefix/protected proofs into parent coverage; a positive page budget fetches the remaining older gaps. Raw responses are saved per request; large normalized timelines checkpoint in batches (up to 25 pages), so an interrupted batch is replayed from cache. `--max-pages` bounds each invocation; rerun to continue. Address writer locks and unique temporary snapshot files prevent overlapping writers. Run `reparse.py` only after all Tron fetches have stopped.

## Source behavior and rate limits

- TronGrid: `/v1/accounts/{address}/transactions`, `/transactions/trc20`, and `/internal-transactions`, with confirmed ascending 200-row pages. Fingerprints are followed; after five full pages the last timestamp is requeried inclusively in a new min/max window. Failed/expired cursors split the time interval. Single-millisecond overflows remain explicit gaps.
- History cutoffs use `/walletsolidity/getnowblock` so the cutoff is confirmed, matching only_confirmed=true. Earlier latest-head cutoffs have their last two minutes requeried after confirmation; proof is in tail_revalidation and data/raw/tron/tail-revalidation-summary.json.gz. Latest account/USDT balances remain separate observations from the latest-state endpoints.
- TRX state: `/wallet/getaccount`; an omitted balance field is recorded as zero under the API default. TRC-10 metadata and reported token balances also come from TronScan. USDT always gets a direct `/wallet/triggerconstantcontract` query, including frozen or unactivated accounts. It is a read-only constant call and broadcasts no transaction.
- TronScan `/api/account` works keylessly and its full account response, including any public tags, is under `data/raw/tron/labels/`. `/api/accountv2` returned 401. Native `/api/transaction` and `/api/token_trc20/transfers` probes are saved under `data/raw/tron/fallback/`. Requests asking for 200 rows returned only 50, and a native type=31 filter returned 401; native sort=timestamp still returned descending rows. Native collection remains on TronGrid. The token fallback validates descending order, address filters, confirmed status and timestamp bounds, follows 50-row offset pages, then restarts inclusively at a timestamp boundary before the 10,000-row explorer cap. Actual pages are saved under data/raw/tron/tronscan_trc20/. Native and fallback token event IDs agree and deduplicate overlapping evidence. Labels remain leads, not controller attribution.
- Saved HTTP 429 bodies report allowed_rps(1), and some later responses report 3, with one- to five-second suspensions. Early polling used 0.5/0.7-second gaps plus response latency and 4/8/16-second backoff. The client enforces a conservative shared 1.2-second minimum between TronGrid request starts across partitions. HTTP 429 responses now impose a shared 6/12/24-second cooldown as well as per-request retry backoff, avoiding competing retries during provider suspensions. Advisory throttle/cooldown files under data/raw/tron/rate-limit are runtime state, not API evidence. HTTP 400/404 probes are distinguishable from collection failures in the saved request URL.
- XRP: `account_tx` (200 rows, forward, validated ledger bound), `account_info`, `account_lines`. Public servers: xrplcluster.com and Ripple s1/s2. RPC tooBusy/slowDown responses specify 2,000 units/10 seconds and 10,000 units/60 seconds. The fetcher now respects the stated retry delay and pins the paging server. Five cross-server cursor boundary gaps in the initial pass were repaired by ledger ranges and verified by AccountRoot continuity. Evidence: `data/raw/other/xrp/continuity-audit.json.gz`.
- Solana: public mainnet-beta RPC, with publicnode/drpc fallbacks; finalized signatures (1,000 rows), JSON-parsed transactions, wallet SOL balance, classic Token and Token-2022 accounts. Raw responses include token-account histories that do not mention the wallet owner. RPC polling used 0.7 seconds plus latency.

- BNB Beacon: legacy dex account state returns five BEP-2/native balances, while its transaction/head APIs return 500/502. The public explorer frontend identifies /api/v1/txs with address, startTime/endTime and page/rows (maximum 100). The working fallback reports 9,091,625 address history records; only the latest 200 and full designation/latest-90-day windows are fetched. Those windows are after the documented 2024-12-03 shutdown and return explicit zero-record responses. The remaining older history is an explicit huge-address gap. Raw evidence is under data/raw/other/bnb/.

| Source | HTTP status | Saved responses | Example raw_ref |
|---|---:|---:|---|
| other | 400 | 1 | `data/raw/other/bnb/explorer-history/errors/92bd5152c080458eaf99febe4f6f36c43639e19e32b4b3d9523ae8a26bce7f29-1792745934647086662.json.gz` |
| other | 404 | 3 | `data/raw/other/bnb/probes/errors/32b5e9824084ae80cc1fbdf7543f11d017816729632b13f18f906c06d513482e-1792745177440620181.json.gz` |
| other | 500 | 2 | `data/raw/other/bnb/probes/errors/79dc0d1ebaaf8a1873b0395926b6f18f5039528fd1c261820ba93b42bc6c25a3-1792745276315128937.json.gz` |
| other | 502 | 13 | `data/raw/other/bnb/history/errors/8df1165524fd300889deb5ab18485cdbcb363d960f7e99111b15785f4ee4c806-1792745496264676894.json.gz` |
| tron | 400 | 1 | `data/raw/tron/internal_probe/errors/4e46fd146011550e66a885dfad96635a5bdcc6b10dc9992c3dc5fc269b4ebd20-1792740981632852983.json.gz` |
| tron | 401 | 3 | `data/raw/tron/fallback/errors/f6a91f64659bccf562cb1ed819d3999599d1be5386219779e9d226cfded68151-1792757989160075298.json.gz` |
| tron | 404 | 1 | `data/raw/tron/internal_probe/errors/cd09fad022a79fa6fe6d12e121da299cc92299bff1c5c280a98fabdc97bd43f5-1792740910559519021.json.gz` |
| tron | 429 | 233 | `data/raw/tron/trc20/errors/4c9440c4b0473c544aa85e0ca01ab64a6ad5df74316082c7e32a0f2c613d0cb2-1792759820627195657.json.gz` |

Application-level XRP rate errors saved: `{'tooBusy': 17, 'slowDown': 1}`. Evidence: `data/raw/tron/source-summary.json.gz`. Counts describe this fetch run, not a guaranteed provider quota.

## Validation

`validate.py` checked 366 timeline files and every transfer/balance raw-reference pointer. Missing timeline files: 0; addresses with contract/provenance errors: 0; addresses with protected-window gaps: 0. Protected coverage is checked by the union of saved millisecond ranges, independently of completion flags. The selected reconciliation sample contains 15 addresses, including the three largest normalized timelines. Across all reported asset balances, 4094 of 4239 checks match within one base unit. Full exact differences, raw refs and cause/limit notes are in `data/raw/tron/validation.json.gz`; successful paging alone is not a balance proof.

| Sample address | Chain | Event rows | raw_ref |
|---|---|---:|---|
| `TXHX2NUvcgft4zs6MkkUtdNVERPTavHDWN` | trx | 223897 | `data/timelines/trx/TXHX2NUvcgft4zs6MkkUtdNVERPTavHDWN.json.gz` |
| `TSmcHwvTR27Ao4NN8HhPFCVcPU5aTEqLDt` | trx | 178825 | `data/timelines/trx/TSmcHwvTR27Ao4NN8HhPFCVcPU5aTEqLDt.json.gz` |
| `TR983hNyUNgrNSB1xncG9thZNhgYpbNvSh` | trx | 148482 | `data/timelines/trx/TR983hNyUNgrNSB1xncG9thZNhgYpbNvSh.json.gz` |
| `TAQPzv9941nVuTj4ng2vd6L11Re57r42pW` | trx | 3871 | `data/timelines/trx/TAQPzv9941nVuTj4ng2vd6L11Re57r42pW.json.gz` |
| `TAYhjpL8pPs8T84FSM329nffQpc6jD8GBM` | trx | 424 | `data/timelines/trx/TAYhjpL8pPs8T84FSM329nffQpc6jD8GBM.json.gz` |
| `bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23` | bnb | 225 | `data/timelines/bnb/bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23.json.gz` |
| `TA82wQ77kb9DieW4C8q7C4KwMfnCzfziqN` | trx | 200 | `data/timelines/trx/TA82wQ77kb9DieW4C8q7C4KwMfnCzfziqN.json.gz` |
| `TA39q3p75XRSWYAEaSF7dANtyksoa3sLge` | trx | 133 | `data/timelines/trx/TA39q3p75XRSWYAEaSF7dANtyksoa3sLge.json.gz` |
| `TASWbk6X1wiTku5TMmMQYqYFvshVEtfJy8` | trx | 131 | `data/timelines/trx/TASWbk6X1wiTku5TMmMQYqYFvshVEtfJy8.json.gz` |
| `6wjqWWra8ombzaw6VHrG5xpQ972jCYF6bbHiFCbWmr4U` | sol | 88 | `data/timelines/sol/6wjqWWra8ombzaw6VHrG5xpQ972jCYF6bbHiFCbWmr4U.json.gz` |
| `TA3941uFAvmVibSkQ6fMJXxmaSNovX86mz` | trx | 31 | `data/timelines/trx/TA3941uFAvmVibSkQ6fMJXxmaSNovX86mz.json.gz` |
| `42RLPACwZPx3vYYmxSueqsogfynBDqXK298EDsNoyoHi` | sol | 24 | `data/timelines/sol/42RLPACwZPx3vYYmxSueqsogfynBDqXK298EDsNoyoHi.json.gz` |
| `FuCC7GoYwt5TsNTjWL23Xx9UKCvC18chjMEFPL3vJDCC` | sol | 15 | `data/timelines/sol/FuCC7GoYwt5TsNTjWL23Xx9UKCvC18chjMEFPL3vJDCC.json.gz` |
| `TA3rH2A7iHnm6pKH8gr9cK1EZnShnmZdFg` | trx | 5 | `data/timelines/trx/TA3rH2A7iHnm6pKH8gr9cK1EZnShnmZdFg.json.gz` |
| `Fc1EwQUZyTEagaDvA1utHXCcZNyG1x2PLt2DfNu1cJdH` | sol | 4 | `data/timelines/sol/Fc1EwQUZyTEagaDvA1utHXCcZNyG1x2PLt2DfNu1cJdH.json.gz` |

Two consecutive incremental refreshes and a completed default rerun succeeded on `TA3941uFAvmVibSkQ6fMJXxmaSNovX86mz`. Network calls were [7, 7, 4]; the completed default rerun made 0 history requests. Proof: `data/raw/tron/incremental-validation.json.gz`, its referenced API responses and three run logs.

XRP and all four Solana wallets passed two consecutive refreshes. A completed default rerun across the other primary-ledger addresses made 0 history requests (head/balance checks only). Proof and refresh logs: `data/raw/other/incremental-validation.json.gz`. Solana refreshes force a fresh first signature page so cached empty results cannot hide later activity. The post-refresh XRP continuity audit is `data/raw/other/xrp/continuity-audit-final.json.gz`.

Empty indexer token metadata was resolved from receipt logs for 5 transfer signatures. Unresolved event records: 0. Evidence: timeline token_resolution/unresolved_events and `data/raw/tron/source-summary.json.gz`.

TronScan token fallback: 632 saved response pages; 31446 normalized event rows currently use that indexer’s evidence. Evidence: `data/raw/tron/source-summary.json.gz`, `scripts/fetch/tron/fallback_tokens.py`, and data/raw/tron/tronscan_trc20/.

Node receipts corrected 6 originator fees that the history indexer reported as zero. The audited events retain indexed_fee_sun and fee_raw_ref; `scripts/fetch/tron/audit_fees.py` and `data/raw/tron/fee-audits/` reproduce these corrections. Other zero-fee indexer rows have not all been independently receipt-audited.

Mismatch categories (counts are address/asset checks):

- 4: Beacon exchange-scale history sampled; full critical windows checked but older native/BEP-2 history is missing, so no zero opening balance can be assumed. Evidence: `data/raw/tron/validation.json.gz`.
- 11: Staking/resource/reward operations are present; their liquid-balance effects are not normalized, and unaudited indexer fees may also differ. Evidence: `data/raw/tron/validation.json.gz`.
- 118: Token Transfer log sum differs from account-reported balance; nonstandard/spam token semantics or indexing omissions (cause unconfirmed). Evidence: `data/raw/tron/validation.json.gz`.
- 12: Unfinished history windows; see coverage.missing_time_windows and saved range proofs. Evidence: `data/raw/tron/validation.json.gz`.

## Coverage limits

- Tron coverage.complete means that confirmed native, internal and TRC-20 paging exhausted for the saved snapshot. TronGrid token/internal records omit block numbers; native transaction/receipt evidence supplies a block when available, with block_raw_ref. TronScan token rows provide their own block; remaining block fields stay null. Token indexes omit log indexes, so identical same-transaction logs at a page boundary can have unresolved multiplicity. These data should not support a claim of zero activity outside the checked range.
- Native staking/unfreezing/reward state changes are retained in raw contract records but not interpreted as ordinary payments. TRC-10 events retain raw quantities; decimals are known only when reported token metadata exists. Transfer logs for rebasing/spam tokens need not reconcile with balance. Tether issuer burns can change USDT balance without Transfer; a discrepancy is not by itself proof of a burn.
- Solana parsed System/SPL transfers are individual rows with is_transfer=true. Network fees and residual balance adjustments are explicit is_transfer=false rows; these may include rent/refunds, mint/burn, ownership changes or unparsed instructions and must not be described as ordinary payments. Old SPL owner omissions are resolved only from chronological explicit initialization/metadata/authority-change evidence, with owner_resolution_raw_refs. Closed token accounts absent from wallet history still prevent a full token-history claim. coverage.complete stays false even when every known signature is parsed. Mint symbols are null rather than guessed.
- Monero is not address-trackable without private view keys; no balance or flow is inferred. Bitcoin-format USDT entries have no asserted token network or token history. Every such bootstrap address has an explicit timeline/coverage record.
- BNB Beacon legacy state is not evidence of current spendability or recovery-contract holdings on BSC. Full older history and multi-send detail remain incomplete; no ownership label or legal conclusion is inferred from the address activity.
- Latest balance observations occur at each request time, not a single atomic chain snapshot. `balance_now[].as_of` and raw request timestamps are authoritative. No designation/checkpoint balances are computed by this collector. The designation-window helper needs official dates in the primary ledger; missing dates are recorded rather than inferred.

The per-address residual windows and unsupported-address list are in the source-specific section of `docs/COVERAGE.md`.
