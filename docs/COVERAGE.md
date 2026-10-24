# Coverage

## Ledger — OFAC address and action evidence

- Outputs: `scripts/ledger/`, `data/ledger.csv`, `data/addresses.csv`, `data/actions.csv`, `data/raw/ofac/`, and `docs/LEDGER.md`.
- Current official exports are dated 2026-10-21. Both SDN XML schemas agree on 1,066 digital-currency features, 1,050 distinct address strings, 1,052 address–entity UID pairs, and 106 entity UID records. The consolidated non-SDN advanced XML has zero digital-currency features.
- Historical-inclusive outputs contain 1,185 address–entity rows, 1,148 chain–address rows, and 75 action dates. All 1,185 rows have a sourced first-publication date and an OFAC UID. Twenty deterministic random rows were source-text reviewed against saved source text; this is not an independent external human audit.
- All 1,391 Recent Actions pages in OFAC's sitemap since 2018-11-28 were saved, including suffixed URLs, with zero fetch failures. Sixty-two 0xB10C list commits and two archived official SDN.XML snapshots supplement the current exports. Completeness is bounded by these sources; OFAC pages no longer exposed in its sitemap may be missing.
- Delistings/removals include Tornado Cash (old UID withdrawn 2022-11-08; replacement UID's 90 addresses removed 2025-03-21), FAYZIMATOV, and individual address removals/corrections from CHATEX, LIFSHITS, SOKOLOVSKI, and ISIL KHORASAN. Removed strings remain in the ledger. Address-feature removal does not imply entity delisting.
- There are 1,171 trackable and 14 untrackable address–entity rows. Current rows comprise 1,040 trackable and 12 untrackable pairs. Monero remains false for privacy; Bitcoin Gold remains false because no usable provider was verified. Three malformed source strings are retained, including two historical corrections. The BNB Beacon Chain historical explorer serves the listed address, despite chain retirement.
- Chain mapping covers every one of the 20 OFAC tickers. Stablecoin EVM assignments use the Ethereum convention with medium confidence because 20-byte hex alone does not establish an EVM network. WANG, Mingming's XBT-labelled `TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq` is a valid Tron address: ticker is preserved, chain is TRX, and `source_ticker_mismatch=true` records the conflict. Tron base58 and equivalent `41`-hex forms are available.
- `ticker`/`chain` are representative fields in the one-row-per-address/UID ledger. Consume `tickers`, `chains`, and `feature_records` to preserve ETH/ETC and ETH/ARB/BSC memberships; `addresses.csv` expands those memberships. Do not add ticker/program counts: they overlap.
- BTC, ETH/ETC/ARB/BSC, TRX, LTC, BCH, BSV, DASH, DOGE, transparent ZEC, XVG, XRP, SOL, and BNB have identified public address-history routes. This ledger section does not validate chain histories. Provider checks encountered 401/403/429 or browser challenges on TRX, BCH, BSC, and SOL; XVG supplied a JavaScript shell. Chain-history checks must verify API access, pagination, earliest retained blocks, and token-history coverage. No balances, flow, freeze, or price completeness is claimed here.
- Current 0xB10C disagreements are exactly three omitted ticker/address pairs (one BNB, two DOGE), with zero 0xB10C-only pairs. Every non-case removal in its saved history has an OFAC-sourced removal row. Full counts, rules, raw paths, and the twenty review excerpts are in `docs/LEDGER.md`.

<!-- freezes:start -->
## Freezes — issuer blacklist event history

- Output: `data/freezes.csv`, 17,248 event logs; reproducible with `scripts/freezes/fetch_freezes.py --check`. Details and dates: `docs/FREEZES.md`.
- ETH USDT (add/remove/destroy) and ETH USDC (blacklist/unblacklist): full Etherscan histories through the documented finalized head. Blockscout full-range comparisons where available, with discrepancies resolved by independent dRPC receipts; HTTP 429 prevented completing every secondary topic. All Ethereum topics also have independent dRPC single-block log samples. See exact ranges and differences in `docs/FREEZES.md`.
- TRX USDT (add/remove/destroy): genesis timestamp through documented solidified head; full ascending/descending TronGrid fingerprint passes agree. Same-indexer retention is a residual uncertainty; TronScan transfer totals are not accepted as blacklist counts.
- Current sets replay transitions, with 20 random active addresses per token and up to 10 cleared addresses checked by latest contract calls. No OFAC matching is performed here.
- Freeze balances: 40/40 sampled Ethereum historical calls available. Other freeze balances are blank. Destruction amounts are burn-time token units, not earlier freeze balances or USD.
- Not covered: USDC Arbitrum/Base/Polygon/Avalanche/Optimism; other USDT chains; Solana freeze-authority instructions.
<!-- freezes:end -->

<!-- fetch_utxo:start -->
## fetch_utxo

Snapshot: 2026-10-23T09:42:26Z. See [UTXO sources](sources/UTXO.md), `scripts/fetch/utxo/fetch.py`, `scripts/fetch/utxo/audit.py`, and `data/raw/utxo/coverage-manifest.json.gz`.

| Ticker | Bootstrap entries | Ledger entries | Audit entries | Complete histories | Coverage entries only | Confirmed address–transaction rows | Source / raw evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| BTC | 532 | 535 | 536 | 535 | 1 | 168682 | https://btc1.trezor.io/api/v2 (Blockbook); https://blockstream.info/api and https://mempool.space/api (Esplora); `data/raw/utxo/coverage-manifest.json.gz#counts.btc` |
| BCH | 7 | 7 | 7 | 7 | 0 | 104 | ssl://bch.imaginary.cash:50002; `data/raw/utxo/coverage-manifest.json.gz#counts.bch` |
| BSV | 1 | 1 | 1 | 1 | 0 | 4 | https://api.whatsonchain.com/v1/bsv/main; `data/raw/utxo/coverage-manifest.json.gz#counts.bsv` |
| BTG | 1 | 1 | 1 | 1 | 0 | 2 | https://btgexplorer.com/api/v2; `data/raw/utxo/coverage-manifest.json.gz#counts.btg` |
| DASH | 5 | 5 | 5 | 5 | 0 | 114 | https://insight.dash.org/insight-api; `data/raw/utxo/coverage-manifest.json.gz#counts.dash` |
| DOGE | 0 | 2 | 2 | 2 | 0 | 19 | https://api.blockcypher.com/v1/doge/main; `data/raw/utxo/coverage-manifest.json.gz#counts.doge` |
| LTC | 13 | 13 | 13 | 13 | 0 | 1170 | https://litecoinspace.org/api; `data/raw/utxo/coverage-manifest.json.gz#counts.ltc` |
| XMR | 11 | 12 | 12 | 0 | 12 | 0 | Untrackable without a view key; https://www.getmonero.org/resources/moneropedia/stealthaddress.html; `data/raw/utxo/coverage-manifest.json.gz#counts.xmr` |
| XVG | 1 | 1 | 1 | 0 | 1 | 0 | No working keyless source found; saved probes; `data/raw/utxo/coverage-manifest.json.gz#counts.xvg` |
| ZEC | 4 | 4 | 4 | 0 | 4 | 0 | No working keyless source found; saved probes; `data/raw/utxo/coverage-manifest.json.gz#counts.zec` |

Independent balance checks: 15 BTC addresses, including the three largest complete histories; 0 mismatches. Full per-address validation is in `data/raw/utxo/validation.json.gz`. Unavailable histories have unknown balances, not zero balances. No controller identities or compliance conclusions are inferred.

- BTC `TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq`: Not a Bitcoin mainnet Base58Check or bc1 witness address. No Bitcoin balance or history is asserted; explorer zero responses are not valid balance observations for this input. The current OFAC-derived ledger resolves this input to TRX; use that chain fetcher. Original bootstrap ticker is preserved here as a coverage entry. Evidence: `data/timelines/btc/TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq.json.gz`.
- XMR `44dZUJ7w1T3fKAvFW8XyXUVoAGSbFvXef2wcbnsjNKGWYorpLJBjth5VKSFhLGkpYKJb2J341tdZHBnbpv72WL7e8zuxfR2`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/44dZUJ7w1T3fKAvFW8XyXUVoAGSbFvXef2wcbnsjNKGWYorpLJBjth5VKSFhLGkpYKJb2J341tdZHBnbpv72WL7e8zuxfR2.json.gz`.
- XMR `45ezvPejNsKYntjhyyeb7fbfzi1sxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/45ezvPejNsKYntjhyyeb7fbfzi1sxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo.json.gz`.
- XMR `45ezvPejNsKYntjhyyeb7fbfzilsxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/45ezvPejNsKYntjhyyeb7fbfzilsxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo.json.gz`.
- XMR `47FVhkRkWgnLs81UBqgY8ui6axAB1627HJjkY2qPnWxMbGfx7387kcY6RzScHgGMQAaH6CBxKXAS4862tS2fhs9BRdmuyav`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/47FVhkRkWgnLs81UBqgY8ui6axAB1627HJjkY2qPnWxMbGfx7387kcY6RzScHgGMQAaH6CBxKXAS4862tS2fhs9BRdmuyav.json.gz`.
- XMR `49HqitRzdnhYjgTEAhgGpCfsjdTeMbUTU6cyR4JV1R7k2Eej9rGT8JpFiYDa4tZM6RZiFrHmMzgSrhHEqpDYKBe5B2ufNsL`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/49HqitRzdnhYjgTEAhgGpCfsjdTeMbUTU6cyR4JV1R7k2Eej9rGT8JpFiYDa4tZM6RZiFrHmMzgSrhHEqpDYKBe5B2ufNsL.json.gz`.
- XMR `5be5543ff73456ab9f2d207887e2af87322c651ea1a873c5b25b7ffae456c320`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/5be5543ff73456ab9f2d207887e2af87322c651ea1a873c5b25b7ffae456c320.json.gz`.
- XMR `84AwzjeFWXNEuhj8LWinXo93AqYr6wS8ZcnaBCoGhrL7EtvBMBovdhiUSV9xLhjrPA8t64hYSaMc8bHtWXoV9129EHUjU62`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/84AwzjeFWXNEuhj8LWinXo93AqYr6wS8ZcnaBCoGhrL7EtvBMBovdhiUSV9xLhjrPA8t64hYSaMc8bHtWXoV9129EHUjU62.json.gz`.
- XMR `86ze8c9oUftDSTxzFBhfSJYpjvw6GYkqjeEaggy3hBVL1ou2tk79DfSj5YiZ3wjDHp541tizcQ8bVCxCtVHQncuc3asa8wz`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/86ze8c9oUftDSTxzFBhfSJYpjvw6GYkqjeEaggy3hBVL1ou2tk79DfSj5YiZ3wjDHp541tizcQ8bVCxCtVHQncuc3asa8wz.json.gz`.
- XMR `87XWTP9tBECHXCwbyMK1KENoy4GeXkRviNzmhNc5Pvo5ExZ1QXjtRRyFeXPuHf7fNiS7KzBZNJeGweJhMbFB647171y66id`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/87XWTP9tBECHXCwbyMK1KENoy4GeXkRviNzmhNc5Pvo5ExZ1QXjtRRyFeXPuHf7fNiS7KzBZNJeGweJhMbFB647171y66id.json.gz`.
- XMR `884Bz8UH63aYsjVdkfWfScRYWZGGNbjFL7pztqvWNSrtYT4reFSwyvkCj9KEGUtheHhhMUj87ciTBFyzoesrMJ4L1FvSoxL`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/884Bz8UH63aYsjVdkfWfScRYWZGGNbjFL7pztqvWNSrtYT4reFSwyvkCj9KEGUtheHhhMUj87ciTBFyzoesrMJ4L1FvSoxL.json.gz`.
- XMR `88wRZuGMuC5YQvXpKpeLFHQeZWW28XtGyZCizkqeypTaRcjzNNKVrCg7PpoEeWaj5A7wwbh5M2X9ycXrfUkbeptACsG4bVn`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/88wRZuGMuC5YQvXpKpeLFHQeZWW28XtGyZCizkqeypTaRcjzNNKVrCg7PpoEeWaj5A7wwbh5M2X9ycXrfUkbeptACsG4bVn.json.gz`.
- XMR `8ANG5NBnApL94YAKRfCSaS7g2fjEi1DWVcFNTn3wQ5HpfsgtnusgxaXE24bbhXukTgF8esRnMsWaReRiqNbSBSbmRE5Nm5M`: Monero hides recipient addresses, amounts and spend linkage; address-level full histories and balances are not publicly trackable without private view keys. Evidence: `data/timelines/xmr/8ANG5NBnApL94YAKRfCSaS7g2fjEi1DWVcFNTn3wQ5HpfsgtnusgxaXE24bbhXukTgF8esRnMsWaReRiqNbSBSbmRE5Nm5M.json.gz`.
- XVG `DFFJhnQNZf8rf67tYnesPu7MuGUpYtzv7Z`: Verge explorer endpoints fail DNS; verge-blockchain.info reports database reorg/maintenance HTTP 503; Cryptoid says hosting expired HTTP 404. No usable history/balance source found. No absence-of-activity inference is supported. No designation-window or recent-90-day history has been fetched. Evidence: `data/timelines/xvg/DFFJhnQNZf8rf67tYnesPu7MuGUpYtzv7Z.json.gz`.
- ZEC `t1LHesgnkapziGQCJtrfZWYXhyjfTVo1dvh`: Transparent-address sources unavailable: Trezor Blockbook HTTP 403; zcha.in HTTP 520; other probes DNS, timeout or TLS failures. No usable history/balance source found. Shielded pool activity cannot be attributed to this transparent address. No absence-of-activity inference is supported. No designation-window or recent-90-day history has been fetched. Evidence: `data/timelines/zec/t1LHesgnkapziGQCJtrfZWYXhyjfTVo1dvh.json.gz`.
- ZEC `t1MMXtBrSp1XG38Lx9cePcNUCJj5vdWfUWL`: Transparent-address sources unavailable: Trezor Blockbook HTTP 403; zcha.in HTTP 520; other probes DNS, timeout or TLS failures. No usable history/balance source found. Shielded pool activity cannot be attributed to this transparent address. No absence-of-activity inference is supported. No designation-window or recent-90-day history has been fetched. Evidence: `data/timelines/zec/t1MMXtBrSp1XG38Lx9cePcNUCJj5vdWfUWL.json.gz`.
- ZEC `t1WSKwCDL1QYRRUrCCknEs5tDLhtGVYu9KM`: Transparent-address sources unavailable: Trezor Blockbook HTTP 403; zcha.in HTTP 520; other probes DNS, timeout or TLS failures. No usable history/balance source found. Shielded pool activity cannot be attributed to this transparent address. No absence-of-activity inference is supported. No designation-window or recent-90-day history has been fetched. Evidence: `data/timelines/zec/t1WSKwCDL1QYRRUrCCknEs5tDLhtGVYu9KM.json.gz`.
- ZEC `t1g7wowvQ8gn2v8jrU1biyJ26sieNqNsBJy`: Transparent-address sources unavailable: Trezor Blockbook HTTP 403; zcha.in HTTP 520; other probes DNS, timeout or TLS failures. No usable history/balance source found. Shielded pool activity cannot be attributed to this transparent address. No absence-of-activity inference is supported. No designation-window or recent-90-day history has been fetched. Evidence: `data/timelines/zec/t1g7wowvQ8gn2v8jrU1biyJ26sieNqNsBJy.json.gz`.

<!-- fetch_utxo:end -->

<!-- fetch_evm-coverage -->

## fetch_evm — EVM address histories

Evidence snapshot: `2026-10-23T10:42:01.135716Z`. Source details and final tables: `docs/sources/EVM.md`.

Produced 1297 address/chain timelines and 2210104 heterogeneous transfer/transaction/pool-event records. Expected pairs without files: 0; malformed input rows explicitly unqueryable: 1. Records and address/chain pairs are different units.

ETH/Arbitrum/Polygon use Etherscan v2 with adaptive block ranges; Optimism uses native Blockscout v2 after the legacy endpoint's persistent HTTP 429s. BSC and Base lack an accessible complete history index under the available free API plan; their state observations and full missing ranges are explicit. ETC uses the available Blockscout instance; see its row and raw errors for actual coverage. Avalanche C support is implemented, but no input row requested that chain.

Identified pools with per-contract validation: 28. Pools use Deposit/Withdrawal RPC logs and independent daily archive balances, with separate event/daily completeness flags. Whole-address completeness is false because unrelated tokens, administrative calls, native donations and ERC20-pool refunds are outside this event scope. Full contract checks and extra-principal differences are retained, not suppressed.

Mandatory ordinary-ETH validation sample: 15 addresses, including three large histories. All available assets are also checked. Results in address/asset-check units: {'matched': 5270, 'inconclusive': 1471, 'mismatched': 2115, 'explained_mismatch': 6}. Unresolved mismatches and source limits remain visible in `data/raw/evm/reports/validation.json.gz`; `coverage.json.gz` has every pair and raw_ref.

A zero current balance or no history found is a statement about data checked. It does not prove no past native/token inflow. Same-address activity on another chain is marked `same address, other chain`; it is not another OFAC-listed address. No issuer freeze or legal conclusion is inferred here.

## fetch_tron — Tron and other account/privacy chains

Final local fetch/validation snapshot: 2026-10-23T13:27:44.450657Z. Inputs `data/addresses.csv`, `data/bootstrap/fetch_tron.csv`; bootstrap commit `6ae2472c439b9bb2788f8df662052ae31854aa97`. Source/method details: `docs/sources/TRON.md`; machine-readable validation: `data/raw/tron/validation.json.gz`.

Counts are distinct address timeline files per chain, not entities or designation actions.

- bnb: 1 address timelines; 0 have completed paging; 225 normalized event rows. Evidence: `data/raw/tron/validation.json.gz`.
- sol: 4 address timelines; 0 have completed paging; 131 normalized event rows. Evidence: `data/raw/tron/validation.json.gz`.
- trx: 341 address timelines; 340 have completed paging; 1450010 normalized event rows. Evidence: `data/raw/tron/validation.json.gz`.
- unknown: 7 address timelines; 0 have completed paging; 0 normalized event rows. Evidence: `data/raw/tron/validation.json.gz`.
- xmr: 12 address timelines; 0 have completed paging; 0 normalized event rows. Evidence: `data/raw/tron/validation.json.gz`.
- xrp: 1 address timelines; 1 have completed paging; 7608 normalized event rows. Evidence: `data/raw/tron/validation.json.gz`.

Tron: confirmed direct native transactions, independent internal transfers and all TRC-20 Transfer pages are queried. Per-asset current balances include direct USDT balanceOf even when frozen. TRC-10 decimal, staking/reward, missing block/log-index and issuer-burn limitations are detailed in the source note. Completed paging is separate from asset reconciliation.

Residual or unsupported histories (each address remains in the dataset):

| Chain | Address | Gap/limit | raw_ref |
|---|---|---|---|
| bnb | `bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23` | Explorer reports 9091625 history records; latest 200 sampled, full designation/latest-90-day windows complete=True; older missing block range in coverage.missing_intervals. Legacy balances are not BSC recovery balances | `data/timelines/bnb/bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23.json.gz` |
| sol | `42RLPACwZPx3vYYmxSueqsogfynBDqXK298EDsNoyoHi` | Known wallet/token-account signatures fetched; closed-account discovery remains incomplete. Parsed transfers and non-payment balance adjustments are separate | `data/timelines/sol/42RLPACwZPx3vYYmxSueqsogfynBDqXK298EDsNoyoHi.json.gz` |
| sol | `6wjqWWra8ombzaw6VHrG5xpQ972jCYF6bbHiFCbWmr4U` | Known wallet/token-account signatures fetched; closed-account discovery remains incomplete. Parsed transfers and non-payment balance adjustments are separate | `data/timelines/sol/6wjqWWra8ombzaw6VHrG5xpQ972jCYF6bbHiFCbWmr4U.json.gz` |
| sol | `Fc1EwQUZyTEagaDvA1utHXCcZNyG1x2PLt2DfNu1cJdH` | Known wallet/token-account signatures fetched; closed-account discovery remains incomplete. Parsed transfers and non-payment balance adjustments are separate | `data/timelines/sol/Fc1EwQUZyTEagaDvA1utHXCcZNyG1x2PLt2DfNu1cJdH.json.gz` |
| sol | `FuCC7GoYwt5TsNTjWL23Xx9UKCvC18chjMEFPL3vJDCC` | Known wallet/token-account signatures fetched; closed-account discovery remains incomplete. Parsed transfers and non-payment balance adjustments are separate | `data/timelines/sol/FuCC7GoYwt5TsNTjWL23Xx9UKCvC18chjMEFPL3vJDCC.json.gz` |
| trx | `TSmcHwvTR27Ao4NN8HhPFCVcPU5aTEqLDt` | native: 2026-05-18T17:02:18Z through 2026-07-10T23:59:59.999000Z; trc20: 2026-04-14T11:14:06Z through 2026-07-10T23:59:59.999000Z; priority windows complete=True; official dates available=True | `data/timelines/trx/TSmcHwvTR27Ao4NN8HhPFCVcPU5aTEqLDt.json.gz` |
| unknown | `16iWn2J1McqjToYLHSsAyS6En3QA8YQ91H` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/16iWn2J1McqjToYLHSsAyS6En3QA8YQ91H.json.gz` |
| unknown | `1CF46Rfbp97absrs7zb7dFfZS6qBXUm9EP` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/1CF46Rfbp97absrs7zb7dFfZS6qBXUm9EP.json.gz` |
| unknown | `1Df883c96LVauVsx9FEgnsourD8DELwCUQ` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/1Df883c96LVauVsx9FEgnsourD8DELwCUQ.json.gz` |
| unknown | `1KUUJPkyDhamZXgpsyXqNGc3x1QPXtdhgz` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/1KUUJPkyDhamZXgpsyXqNGc3x1QPXtdhgz.json.gz` |
| unknown | `1LrxsRd7zNuxPJcL5rttnoeJFy1y4AffYY` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/1LrxsRd7zNuxPJcL5rttnoeJFy1y4AffYY.json.gz` |
| unknown | `3E6ZCKRrsdPc35chA9Eftp1h3DLW18NFNV` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/3E6ZCKRrsdPc35chA9Eftp1h3DLW18NFNV.json.gz` |
| unknown | `3LtcaPbCj87CwJHnRX3vh7c2y9RZQqeSy8` | Bitcoin-format USDT ticker entry; token network unresolved, token-layer history not fetched | `data/timelines/unknown/3LtcaPbCj87CwJHnRX3vh7c2y9RZQqeSy8.json.gz` |
| xmr | `44dZUJ7w1T3fKAvFW8XyXUVoAGSbFvXef2wcbnsjNKGWYorpLJBjth5VKSFhLGkpYKJb2J341tdZHBnbpv72WL7e8zuxfR2` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/44dZUJ7w1T3fKAvFW8XyXUVoAGSbFvXef2wcbnsjNKGWYorpLJBjth5VKSFhLGkpYKJb2J341tdZHBnbpv72WL7e8zuxfR2.json.gz` |
| xmr | `45ezvPejNsKYntjhyyeb7fbfzi1sxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/45ezvPejNsKYntjhyyeb7fbfzi1sxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo.json.gz` |
| xmr | `45ezvPejNsKYntjhyyeb7fbfzilsxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/45ezvPejNsKYntjhyyeb7fbfzilsxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo.json.gz` |
| xmr | `47FVhkRkWgnLs81UBqgY8ui6axAB1627HJjkY2qPnWxMbGfx7387kcY6RzScHgGMQAaH6CBxKXAS4862tS2fhs9BRdmuyav` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/47FVhkRkWgnLs81UBqgY8ui6axAB1627HJjkY2qPnWxMbGfx7387kcY6RzScHgGMQAaH6CBxKXAS4862tS2fhs9BRdmuyav.json.gz` |
| xmr | `49HqitRzdnhYjgTEAhgGpCfsjdTeMbUTU6cyR4JV1R7k2Eej9rGT8JpFiYDa4tZM6RZiFrHmMzgSrhHEqpDYKBe5B2ufNsL` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/49HqitRzdnhYjgTEAhgGpCfsjdTeMbUTU6cyR4JV1R7k2Eej9rGT8JpFiYDa4tZM6RZiFrHmMzgSrhHEqpDYKBe5B2ufNsL.json.gz` |
| xmr | `5be5543ff73456ab9f2d207887e2af87322c651ea1a873c5b25b7ffae456c320` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/5be5543ff73456ab9f2d207887e2af87322c651ea1a873c5b25b7ffae456c320.json.gz` |
| xmr | `84AwzjeFWXNEuhj8LWinXo93AqYr6wS8ZcnaBCoGhrL7EtvBMBovdhiUSV9xLhjrPA8t64hYSaMc8bHtWXoV9129EHUjU62` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/84AwzjeFWXNEuhj8LWinXo93AqYr6wS8ZcnaBCoGhrL7EtvBMBovdhiUSV9xLhjrPA8t64hYSaMc8bHtWXoV9129EHUjU62.json.gz` |
| xmr | `86ze8c9oUftDSTxzFBhfSJYpjvw6GYkqjeEaggy3hBVL1ou2tk79DfSj5YiZ3wjDHp541tizcQ8bVCxCtVHQncuc3asa8wz` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/86ze8c9oUftDSTxzFBhfSJYpjvw6GYkqjeEaggy3hBVL1ou2tk79DfSj5YiZ3wjDHp541tizcQ8bVCxCtVHQncuc3asa8wz.json.gz` |
| xmr | `87XWTP9tBECHXCwbyMK1KENoy4GeXkRviNzmhNc5Pvo5ExZ1QXjtRRyFeXPuHf7fNiS7KzBZNJeGweJhMbFB647171y66id` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/87XWTP9tBECHXCwbyMK1KENoy4GeXkRviNzmhNc5Pvo5ExZ1QXjtRRyFeXPuHf7fNiS7KzBZNJeGweJhMbFB647171y66id.json.gz` |
| xmr | `884Bz8UH63aYsjVdkfWfScRYWZGGNbjFL7pztqvWNSrtYT4reFSwyvkCj9KEGUtheHhhMUj87ciTBFyzoesrMJ4L1FvSoxL` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/884Bz8UH63aYsjVdkfWfScRYWZGGNbjFL7pztqvWNSrtYT4reFSwyvkCj9KEGUtheHhhMUj87ciTBFyzoesrMJ4L1FvSoxL.json.gz` |
| xmr | `88wRZuGMuC5YQvXpKpeLFHQeZWW28XtGyZCizkqeypTaRcjzNNKVrCg7PpoEeWaj5A7wwbh5M2X9ycXrfUkbeptACsG4bVn` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/88wRZuGMuC5YQvXpKpeLFHQeZWW28XtGyZCizkqeypTaRcjzNNKVrCg7PpoEeWaj5A7wwbh5M2X9ycXrfUkbeptACsG4bVn.json.gz` |
| xmr | `8ANG5NBnApL94YAKRfCSaS7g2fjEi1DWVcFNTn3wQ5HpfsgtnusgxaXE24bbhXukTgF8esRnMsWaReRiqNbSBSbmRE5Nm5M` | Untrackable publicly: private view keys required; no balance/flow inference | `data/timelines/xmr/8ANG5NBnApL94YAKRfCSaS7g2fjEi1DWVcFNTn3wQ5HpfsgtnusgxaXE24bbhXukTgF8esRnMsWaReRiqNbSBSbmRE5Nm5M.json.gz` |

No outflow found means only within the saved data checked. The fetcher never infers controller identities or legal violations. Solana wallet SOL balances and XRP AccountRoot balances are validated independently from completeness claims.
