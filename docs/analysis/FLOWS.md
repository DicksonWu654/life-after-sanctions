# Post-designation outflows — completed bounded snapshot

Snapshot: **2026-10-23T20:57:57.609971+00:00**. **1,147 of 1,148 ledger chain-address pairs** had readable timelines. Data as of 2026-10-23; bounded acquisition is complete and source-specific history gaps remain. Every conclusion below means **within data checked**.

Observed wallet gross outflows: **$2,489,419,653.78 USD at transfer time**, across **1,557 transfer/net-debit edges** from **101 chain-address pairs**. This is gross turnover, not unique funds or value at designation.

## Reproduce

```sh
.venv/bin/python scripts/analysis/flows.py
.venv/bin/python scripts/analysis/trace.py --fetch
.venv/bin/python scripts/analysis/flows.py --resume
.venv/bin/python scripts/analysis/flows.py --check
.venv/bin/python scripts/analysis/flows.py --self-test
```

Default scans current inputs; `--resume` and `--check` use the immutable published snapshot so concurrent timeline refreshes cannot silently change its cohort. `--check` reruns edge construction, classification, prices, selection, aggregation and Markdown/CSV generation; it rejects changed shared label/price dependencies and mismatched outputs. A fresh default run adopts newer timelines. No credentials, installs or third-party execution are needed.

Snapshot evidence: `data/raw/flows/snapshots/0b0395ea222c96ed25e081ca747fd80c7fe4e9ccfa8c62f6ac3490798a362210.json.gz`. Each source timeline has a compressed-file SHA-256; only post-T candidate outgoing rows are copied to this gzip snapshot, preserving original raw pointers. Ledger/address tables and coverage rows are frozen in the same snapshot. Source responses remain under their original raw directories. The edge CSV has transaction raw references, source explorer URLs, exact amounts, price observation time/raw references and all competing source label claims.

## Definitions and limits

- The unit is a chain-address pair from addresses.csv. T is the start of its first-listed date in Eastern Time; intraday publication order is unknown. The requested after-T window continues after removals; that is not a claim of continuing sanctions.
- Include successful positive native transfers and exact-contract/decimal-allowlisted tokens. Unknown tokens remain in the CSV as unpriced; a token symbol cannot establish value. No USD=1 stablecoin assumption. Prices use price.usd(), hourly observations when fresh, otherwise daily; every row records the actual observation time. No interpolation or today-price backfill.
- Main Sankey excludes source Tornado pool/router contracts, same-address transfers and priced values below USD 1. Functional Tornado source classification uses the labels lookup. Pool beneficiary/relayer splits are decoded from saved events and shown separately. Transfers between different addresses sharing an OFAC UID remain visible and flagged.
- Single-source UTXO transactions retain each non-return output. Mixed-input outputs appear as candidate evidence with included_in_total=false; their full values are never attributed to the listed input. The listed address net debit excluding its fetcher-allocated fee appears once as an unlabelled/unallocated edge. Change to the same address is excluded; change to a new address cannot be identified. These are address transfers, not proof of external economic payments.
- XRPL net balance debits without a proven recipient stay unallocated. SOL balance adjustments are excluded when is_transfer=false. Unreadable JSON/gzip files are skipped and counted; .tmp/.part files are ignored and counted. A valid incomplete history is retained with complete=false. Missing transfer timestamps are excluded and counted; no inferred timestamp is used.
- Destination roles: mixer, bridge, dex, cex_deposit, cex_hot, other_sanctioned, issuer, defi_other, unlabelled. Conflicting functional roles become unlabelled. other_sanctioned requires its source validity interval at transfer time. Generic exchange names do not prove deposit/hot roles. Public labels are leads, not ownership findings; historical service-label validity is usually unknown.
- Each program-tagged edge is split equally across its distinct program tags in the program view; the chain view assigns it once. Both link sets conserve the same total and are alternatives. Site mapping folds cex_hot into cex_deposit, issuer/defi_other into unlabelled. Stocks still_there/frozen are omitted from a gross-flow Sankey to avoid mixing units.

Excluding exchange-scale source addresses (>10,000 distinct transaction hashes), the wallet total is **$2,487,118,755.87 USD at transfer time**. Separate source-Tornado gross outflows are **$11,935,755,348.64 USD at transfer time**, with timestamp/token gaps. There are **41,767 unpriced evidence edges** and **$3,082,881.71 USD at transfer time** with unallocated recipients.

## Candidate findings

### flows-mixer-paths

4 selected first-hop receipt paths reached a mixer-labelled destination at hop counts 3, counting the listed-address transfer as hop 1.

**Unit/valuation:** events; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** Observed same-asset temporal paths under the FIFO/largest-output rule; public protocol labels have raw sources. This does not attribute the full seed amount to the terminal transfer. Dates in the examples are essential: a mixer role does not mean the service was designated at that time; Tornado Cash was first designated on 2022-08-08.

- [0x506843f36f6389a2e88e12ae5dbeab8b2f6443d2e4a1d27f4f89b3631992a0fb](https://etherscan.io/tx/0x506843f36f6389a2e88e12ae5dbeab8b2f6443d2e4a1d27f4f89b3631992a0fb) — 2022-05-02T02:50:29Z; price observed 2022-05-02T02:00:00Z; `data/raw/flows/http_objects/d43dd7ba27e8ee16c3a1e72c09d308d7d53ccfba867b194927ec7061b1321b07.json.gz#/response/items/17`.
- [0x8470d372429d9fde871624ee33e82f228a9a7e5283302f939e804fc4d5ce385e](https://etherscan.io/tx/0x8470d372429d9fde871624ee33e82f228a9a7e5283302f939e804fc4d5ce385e) — 2022-05-05T07:41:57Z; price observed 2022-05-05T07:00:00Z; `data/raw/flows/http_objects/5b3b829f20b25ad23e8dc26446c0ab21d628842859277970777e4c0b7b05ca2c.json.gz#/response/items/9`.
- [0xc64e2859ae45ba4b0eceaa7670e46be27a4ce4e04aa8976f190a6cb9c8464c6d](https://etherscan.io/tx/0xc64e2859ae45ba4b0eceaa7670e46be27a4ce4e04aa8976f190a6cb9c8464c6d) — 2022-05-10T13:25:53Z; price observed 2022-05-10T13:00:00Z; `data/raw/flows/http_objects/c55103cbd37fdd6c388fd4f91a057a0b2fcbd8f866b709f331325124bd34c677.json.gz#/response/items/30`.

### flows-within-entity

1,341,710.31 USD of observed gross outflows moved between addresses sharing an OFAC entity UID.

**Unit/valuation:** usd; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** High confidence in shared OFAC UID; both addresses were listed by transfer time. This is a gross internal movement measure, not additional money leaving the entity. Provisional timeline coverage.

- [0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73](https://etherscan.io/tx/0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73) — 2023-11-27T02:43:11Z; price observed 2023-11-27T02:00:00Z; `data/raw/evm/etherscan/27b540ad264d383622b8bc80.json.gz#/response/result/18`.
- [e28489bfc229a94c57b18177122d79647550bd3d429735657d8230de69461dc3](https://tronscan.org/#/transaction/e28489bfc229a94c57b18177122d79647550bd3d429735657d8230de69461dc3) — 2024-03-20T15:49:03Z; price observed 2024-03-20T15:00:00Z; `data/raw/tron/native/26acd55f530e616da03a8d4eeb3ebedcc6d461ad79409f0d28642b54c7c7d424.json.gz#/response/data/111`.
- [db321663aa95651258645e545bbddcef4bf511a8143f94700da72a6d5e2caaa2](https://tronscan.org/#/transaction/db321663aa95651258645e545bbddcef4bf511a8143f94700da72a6d5e2caaa2) — 2026-07-02T20:09:30Z; price observed 2026-07-02T20:00:00Z; `data/raw/tron/native/6acf5d7926b5e223872c3647a6b877bd654cbc91bea39dc1938630a79e83accd.json.gz#/response/data/71`.

### flows-chen-seizure-confounder

Addresses OFAC lists under CHEN, Zhi sent 1,722,913,707.06 USD after their identifier designation, including 4 Bitcoin output edges on 2025-10-22; destination labels are limited by the public label set.

**Unit/valuation:** usd; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** High confidence in amounts and OFAC source-address membership, provisional coverage. Do not describe this as evasion: the saved TRM account of the 2025-10-14 action reports a contemporaneous DOJ forfeiture and government custody. That context does not establish the owner of these particular recipient addresses.

Context source: [https://www.trmlabs.com/resources/blog/historic-u-s--u-k-operation-targets-southeast-asias-scam-compounds-with-record-15-billion-bitcoin-seizure](https://www.trmlabs.com/resources/blog/historic-u-s--u-k-operation-targets-southeast-asias-scam-compounds-with-record-15-billion-bitcoin-seizure); `data/raw/priorart/pages/trm-prince.txt.gz`.

- [c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24](https://mempool.space/tx/c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24) — 2025-10-22T10:35:44Z; price observed 2025-10-22T10:00:00Z; `data/raw/utxo/btc1.trezor.io/0a/0ad65fa1eecd9b209198c537739f4f12fe9e3841bd672431f8e48462a93278d1-d431f26e91059872.json.gz#response.transactions[0]`.
- [b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885](https://mempool.space/tx/b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885) — 2025-10-22T11:40:02Z; price observed 2025-10-22T11:00:00Z; `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[0]`.
- [e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d](https://mempool.space/tx/e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d) — 2025-10-22T10:16:38Z; price observed 2025-10-22T10:00:00Z; `data/raw/utxo/btc1.trezor.io/ad/ad5196fbd51b3e7b5f6e8ef2ae314eae2fde8fd1c61273837db96e3f1ee6c77f-a9cff8ff8e5389c8.json.gz#response.transactions[0]`.

### flows-unlabelled-first-hop

99.85% of observed wallet outflow USD at transfer time has an unlabelled first-hop role in the saved public label set.

**Unit/valuation:** share; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** High confidence as a description of this dataset, not of actual service use. Generic exchange tags, unresolved output attribution and scarce BTC/Tron service labels remain unlabelled. A zero first-hop mixer/CEX count is not evidence that no mixer/CEX was reached later.

- [c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24](https://mempool.space/tx/c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24) — 2025-10-22T10:35:44Z; price observed 2025-10-22T10:00:00Z; `data/raw/utxo/btc1.trezor.io/0a/0ad65fa1eecd9b209198c537739f4f12fe9e3841bd672431f8e48462a93278d1-d431f26e91059872.json.gz#response.transactions[0]`.
- [b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885](https://mempool.space/tx/b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885) — 2025-10-22T11:40:02Z; price observed 2025-10-22T11:00:00Z; `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[0]`.
- [e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d](https://mempool.space/tx/e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d) — 2025-10-22T10:16:38Z; price observed 2025-10-22T10:00:00Z; `data/raw/utxo/btc1.trezor.io/ad/ad5196fbd51b3e7b5f6e8ef2ae314eae2fde8fd1c61273837db96e3f1ee6c77f-a9cff8ff8e5389c8.json.gz#response.transactions[0]`.

### flows-direct-bridge

Listed source wallets sent 16,318.59 USD directly to destinations classified bridge, within the timelines checked.

**Unit/valuation:** usd; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** Provisional. Transfer amounts have raw evidence; public service labels are leads, often without historical validity. Gross transfers can recirculate; amounts are not unique funds or proof of unlawful conduct.

- [0xf1057c81d9ec661437485a0e224fc94e22e2cfc6717c2d79471bfb8ba25cf443](https://etherscan.io/tx/0xf1057c81d9ec661437485a0e224fc94e22e2cfc6717c2d79471bfb8ba25cf443) — 2022-04-19T18:25:16Z; price observed 2022-04-19T18:00:00Z; `data/raw/evm/etherscan/8b7802e62c291b1bb9b1ae17.json.gz#/response/result/395`.
- [0xc080576546f2561e67a5dfadd050934019b8064da2292ece3ddd9e02052cbc3a](https://etherscan.io/tx/0xc080576546f2561e67a5dfadd050934019b8064da2292ece3ddd9e02052cbc3a) — 2021-11-18T17:26:53Z; price observed 2021-11-18T17:00:00Z; `data/raw/evm/etherscan/09a1e8425ada2d0a67ab0995.json.gz#/response/result/405`.
- [0x4e78976e75b7750f37f7da5252ddfa5baf9dfc33600c77a21f6d6e98e1a377bc](https://etherscan.io/tx/0x4e78976e75b7750f37f7da5252ddfa5baf9dfc33600c77a21f6d6e98e1a377bc) — 2021-11-18T17:43:05Z; price observed 2021-11-18T17:00:00Z; `data/raw/evm/etherscan/09a1e8425ada2d0a67ab0995.json.gz#/response/result/406`.

### flows-direct-dex

Listed source wallets sent 30,194.45 USD directly to destinations classified dex, within the timelines checked.

**Unit/valuation:** usd; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** Provisional. Transfer amounts have raw evidence; public service labels are leads, often without historical validity. Gross transfers can recirculate; amounts are not unique funds or proof of unlawful conduct.

- [0x21b6a526852d4e21a78e0609f02f3d82b28086f9aae4323142a13f5e10326b7a](https://etherscan.io/tx/0x21b6a526852d4e21a78e0609f02f3d82b28086f9aae4323142a13f5e10326b7a) — 2021-12-02T17:47:03Z; price observed 2021-12-02T17:00:00Z; `data/raw/evm/etherscan/09a1e8425ada2d0a67ab0995.json.gz#/response/result/435`.
- [0xd07b56d95789abb1d6e41626177fbd458e75ad91ad590369393c328a67181b82](https://etherscan.io/tx/0xd07b56d95789abb1d6e41626177fbd458e75ad91ad590369393c328a67181b82) — 2021-12-02T17:48:27Z; price observed 2021-12-02T17:00:00Z; `data/raw/evm/etherscan/09a1e8425ada2d0a67ab0995.json.gz#/response/result/436`.
- [0x1b76335f45ebb16fa1f05b478ba4840e3a4a1ecd080789904c246dd41c1c2b15](https://etherscan.io/tx/0x1b76335f45ebb16fa1f05b478ba4840e3a4a1ecd080789904c246dd41c1c2b15) — 2024-04-06T09:47:35Z; price observed 2024-04-06T09:00:00Z; `data/raw/evm/etherscan/09a1e8425ada2d0a67ab0995.json.gz#/response/result/544`.

### flows-direct-other_sanctioned

Listed source wallets sent 1,341,710.31 USD directly to destinations classified other_sanctioned, within the timelines checked.

**Unit/valuation:** usd; dollar values use saved observations at or before each transfer (actual timestamps in CSV). Events are transfer edges. **Confidence:** Provisional. Transfer amounts have raw evidence; public service labels are leads, often without historical validity. Gross transfers can recirculate; amounts are not unique funds or proof of unlawful conduct.

- [0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73](https://etherscan.io/tx/0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73) — 2023-11-27T02:43:11Z; price observed 2023-11-27T02:00:00Z; `data/raw/evm/etherscan/27b540ad264d383622b8bc80.json.gz#/response/result/18`.
- [e28489bfc229a94c57b18177122d79647550bd3d429735657d8230de69461dc3](https://tronscan.org/#/transaction/e28489bfc229a94c57b18177122d79647550bd3d429735657d8230de69461dc3) — 2024-03-20T15:49:03Z; price observed 2024-03-20T15:00:00Z; `data/raw/tron/native/26acd55f530e616da03a8d4eeb3ebedcc6d461ad79409f0d28642b54c7c7d424.json.gz#/response/data/111`.
- [db321663aa95651258645e545bbddcef4bf511a8143f94700da72a6d5e2caaa2](https://tronscan.org/#/transaction/db321663aa95651258645e545bbddcef4bf511a8143f94700da72a6d5e2caaa2) — 2026-07-02T20:09:30Z; price observed 2026-07-02T20:00:00Z; `data/raw/tron/native/6acf5d7926b5e223872c3647a6b877bd654cbc91bea39dc1938630a79e83accd.json.gz#/response/data/71`.

## First-hop destination classes

| Class | USD at transfer time | Edges |
| --- | ---: | ---: |
| mixer | 0.00 | 0 |
| bridge | 16,318.59 | 6 |
| dex | 30,194.45 | 19 |
| cex_deposit | 780.82 | 2 |
| cex_hot | 10,005.71 | 3 |
| other_sanctioned | 1,341,710.31 | 6 |
| issuer | 0.00 | 0 |
| defi_other | 2,299,044.44 | 682 |
| unlabelled | 2,485,721,599.48 | 839 |

## Named first-hop destinations

Names below are verbatim public-source labels or OFAC names. They establish a lookup match, not current ownership or legal knowledge. USD is valued at transfer time; labels may lack historical validity. Full source claims and example transactions are in top_named_destinations in results/flows.json.

| Source label | Chain | Class | USD at transfer time | Label confidence |
| --- | --- | --- | ---: | --- |
| Wrapped Ether | ETH | defi_other | 2,299,044.44 | medium |
| OFAC listed: SEMENOV, Roman | ETH | other_sanctioned | 1,341,519.11 | high |
| Uniswap: Universal Router; Uniswap: Universal Router v1.2 | ETH | dex | 14,012.03 | medium |
| Avalanche: Old Bridge | ETH | bridge | 12,181.82 | medium |
| Binance-Hot 7 | TRX | cex_hot | 10,005.71 | medium |
| SushiSwap: Router | ETH | dex | 8,974.66 | medium |
| Blockscout public tag: Bridge | ETH | bridge | 4,002.01 | medium |
| Uniswap V3: USDC 3 | ETH | dex | 3,900.09 | medium |
| Uniswap V2: Router 2 | ETH | dex | 2,270.29 | medium |
| Binance Deposit: 0xa01bd7860cbb705a1a0c9bf4c98470516462b71f | ETH | cex_deposit | 707.28 | medium |
| 1inch v5: Aggregation Router; Aggregation Router V5 | ETH | dex | 559.03 | medium |
| 0x: Exchange Proxy | ETH | dex | 278.34 | low, medium |

## Multi-hop coverage and rule

First receipt is hop 1. Process selected first-hop receipts FIFO by time/block/hash. At each unlabelled address select its earliest later outgoing transaction of the same exact asset; if that transaction has multiple outputs follow its largest output (ties: destination then event id). Reserve that outgoing transaction once across FIFO paths; do not substitute its smaller outputs, split or proportionally haircut lots. Stop at the first labelled class, unresolved ordering/coverage, repeated address, or hop 5. This is a temporal path heuristic, not a balance-aware FIFO taint accounting system: earlier unrelated balances, mixing and ownership are unknown. Original USD is a seed-weight only; no downstream USD attribution.

Largest-value selection: **8 destination chain-address pairs**, representing **$2,028,112,836.38 / $2,485,721,599.48 unlabelled first-hop USD at transfer time (81.59%)**. Target ≥80%, cap 400; target met: **True**. Unallocated synthetic destinations cannot be traced and remain in the denominator. Selection is across all covered chains; unsupported chains are reported, not silently dropped.

Attempted selected destinations: **8 chain-address pairs**; path outcomes: `{"label_reached": 4, "no_outgoing_observed": 4}`. The full trace bundle is `data/raw/flows/traces/5d5ab3a4a5b78a593fb3c63319c8f7f053a5a0bf597e283c59f1ff997ac3645c.json.gz`. Original first-hop USD weights are not amounts proven received by downstream services. Paths stop at any labelled class; a bridge/DEX terminal is censored for mixer/CEX reachability and asset conversions are not guessed.

Keyless GET requests only: Blockscout for supported EVM networks, Trezor Blockbook for supported UTXO chains, TronGrid for Tron. At most one request start per host per 1.25 seconds, bounded exponential backoff on 429, resumable successful raw caching. No Etherscan requests. Errors, pagination limits, host circuit-breaks and unknown ordering are explicit terminal outcomes; these must not be interpreted as zero hops or no service reached.

### First mixer/CEX reached (conditional on observed paths)

| Class | Hops including first receipt | Paths | Original seed USD weight at first-transfer time |
| --- | ---: | ---: | ---: |
| mixer | 3 | 4 | 305,199,129.32 |
| cex_deposit | 1 | 2 | 780.82 |
| cex_hot | 1 | 3 | 10,005.71 |

Seed weights are not downstream amounts received. No CEX label reached within checked paths is a censored observation, not proof no exchange was used. Terminal txs and full intermediate paths, amounts and labels are retained in the trace bundle.

## Per-chain coverage (within data checked)

| Chain | Ledger pairs | Readable timelines | Complete histories | Missing | Untrackable | USD at transfer time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ARB | 1 | 1 | 1 | 0 | 0 | 0.00 |
| BCH | 7 | 7 | 7 | 0 | 0 | 153.99 |
| BNB | 1 | 1 | 0 | 0 | 0 | 0.00 |
| BSC | 1 | 1 | 0 | 0 | 0 | 0.00 |
| BSV | 1 | 1 | 1 | 0 | 0 | 0.00 |
| BTC | 535 | 535 | 535 | 0 | 0 | 1,726,036,980.92 |
| BTG | 1 | 1 | 1 | 0 | 1 | 0.00 |
| DASH | 5 | 5 | 5 | 0 | 0 | 0.00 |
| DOGE | 2 | 2 | 2 | 0 | 0 | 0.00 |
| ETC | 1 | 1 | 1 | 0 | 0 | 0.00 |
| ETH | 217 | 216 | 188 | 1 | 1 | 762,949,929.18 |
| LTC | 13 | 13 | 13 | 0 | 0 | 114.37 |
| SOL | 4 | 4 | 0 | 0 | 0 | 0.00 |
| TRX | 341 | 341 | 340 | 0 | 0 | 431,349.25 |
| XMR | 12 | 12 | 0 | 0 | 12 | 0.00 |
| XRP | 1 | 1 | 1 | 0 | 0 | 1,126.06 |
| XVG | 1 | 1 | 0 | 0 | 0 | 0.00 |
| ZEC | 4 | 4 | 0 | 0 | 0 | 0.00 |

Unreadable files: 0; in-progress files ignored: 0; candidate outgoing rows without exact time: 87. Full per-address source coverage notes and missing ranges are in the snapshot.

## What this adds to prior work

Liu et al. arXiv 2507.11721v2 already trace Ethereum destinations, bridges and service interactions using proportional exposure; Zola et al. 2409.10031 already examine Bitcoin one/two-step service graphs. This output supplies a public-ledger chain-address cohort, transfer-time valuation, source-linked first-hop Sankey alternatives, temporal label handling and an explicit five-hop largest-output path heuristic with failed/partial paths retained. It does not claim a new tracing invention, full-chain coverage, causality, or parity with vendors’ private clusters. See docs/PRIOR_ART.md and the binding docs/DEFINITIONS.md.

## Execution scope and open uncertainties


Coverage is uneven by chain and changes during acquisition. Sparse Tron/BTC CEX labels can make a service appear unlabelled. Historical label deployment/ownership is usually unverified. Successful API pagination is not independent chain-node validation; provider result caps can prevent ordering proof. Gross same-entity movements and address reuse can dominate a Sankey without measuring new money. First-hop unknown-token quantities cannot be valued safely. Exact publication-time ambiguity, incomplete histories and post-delisting observations limit headline interpretation.

Research, not legal or compliance advice. “Received funds from a sanctioned address” describes an observed chain relationship, not unlawful conduct. Exchanges may have frozen or reported funds. Names in outputs are verbatim source labels or OFAC names; no unlabelled address owner is inferred.

## Public chart grouping

The compact chart labels `unlabelled + defi_other` as **Other / unclassified** and `cex_deposit + cex_hot` as **Exchange-labelled address**. It separately displays the original unknown-role share and original DeFi, deposit and hot-wallet subtotals from `results/flows.json#summary.classes`, valued at each transfer time. Gross first-hop transfers can count funds repeatedly. The public export derives these fields with `scripts/release/presentation.py`; raw API captures are omitted for size and request identities can be re-fetched through the pipeline.
