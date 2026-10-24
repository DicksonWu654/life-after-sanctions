# Tornado Cash — completed bounded snapshot legal-event case study

Snapshot: 2026-10-23T10:09:31Z. `provisional: false`. Rebuild with `.venv/bin/python scripts/analysis/tornado.py`; add `--fetch` for cached keyless gap filling. Reproduce the pinned snapshot with `--check` against the saved acquisition record.

Coverage: **91 / 91 ledger chain–addresses** have readable timelines. 455 readable Tornado-related timeline files across five checked chains; 0 unreadable/partial files skipped. 28 identified ETH-chain pool contracts, including 4 native ETH pools. 0 native-pool events still lack a proven UTC date.

## What changed around each legal event?

Equal 30-day UTC windows exclude the event date. These are descriptive changes, not causal estimates. Native ETH amounts count pool principal; USD revalues each day's flow at its saved closing observation. The complete per-pool series, actual price times, independent TVL observation times and raw references are in `data/derived/tornado_daily.csv`.

| Event | Deposits before, ETH | Deposits after, ETH | Change | Withdrawals before, ETH | Withdrawals after, ETH | Nonzero relayer share before → after |
|---|---:|---:|---:|---:|---:|---:|
| [2022-08-08](https://ofac.treasury.gov/recent-actions/20220808) Initial OFAC designation | 109,626.4 | 35,125.7 | -67.96% | 96,339.1 | 148,277.8 | 99.9% → 98.7% |
| [2022-11-08](https://ofac.treasury.gov/recent-actions/20221108) Withdrawal and immediate re-designation | 22,369.9 | 19,486.8 | -12.89% | 13,023.0 | 23,626.0 | 95.2% → 95.9% |
| [2024-11-26](https://www.ca5.uscourts.gov/opinions/pub/23/23-50669-CV0.pdf) Van Loon Fifth Circuit ruling | 27,134.1 | 28,507.2 | +5.06% | 32,764.4 | 37,885.0 | 87.2% → 77.7% |
| [2025-03-21](https://ofac.treasury.gov/recent-actions/20250321) OFAC removal | 17,760.1 | 45,235.4 | +154.70% | 24,976.8 | 48,170.3 | 76.4% → 87.3% |

The formal removal has the largest positive native-volume change among these equal-window comparisons. The ruling coincides with a much larger reaction in TORN's sampled market price than in ETH deposits. At the initial designation, fewer distinct transaction origins and higher withdrawals accompany the fall in deposits; these observations do not isolate sanctions from other causes.

### Candidate findings and transaction examples

- **OFAC removal: ETH deposits changed +154.70% in equal 30-day windows (17,760.1 → 45,235.4 ETH).** Confidence: Descriptive before/after comparison, equal UTC windows excluding event date; publication time unknown; not an estimate of causal effect. Counts cross-checked against pool nextIndex; source gaps remain explicit in coverage.
  - [0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec](https://etherscan.io/tx/0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec) (2025-03-23, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/768a90a0e23a5b4cd0bfbe4b.json.gz#/response/result/1370`.
  - [0xf90c405ae2b8fb2cde2b46da5a5a01c5ad2ddb46b5cecaed4f9d03a41537b9bf](https://etherscan.io/tx/0xf90c405ae2b8fb2cde2b46da5a5a01c5ad2ddb46b5cecaed4f9d03a41537b9bf) (2025-03-22, pool `0x910cbd523d972eb0a6f4cae4618ad62622b39dbf`); `data/raw/evm/rpc/6e2e217738416be11ab3ca36.json.gz#/response/result/3249`.
  - [0x5d93a2e859d897eefa3ecf94fe24d285f289077eb5b734f16ae67a17ae2c7662](https://etherscan.io/tx/0x5d93a2e859d897eefa3ecf94fe24d285f289077eb5b734f16ae67a17ae2c7662) (2025-03-22, pool `0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936`); `data/raw/evm/rpc/89dd4c4962c92eb868d0fd94.json.gz#/response/result/3310`.
- **Around Van Loon, sampled TORN price rose 458.17%; ETH deposits in the surrounding 30-day windows rose 5.06%.** Confidence: Different time horizons: price uses explicitly timestamped November 25/27 samples, protocol use uses equal 30-day windows. Market data is not inferred from these illustrative pool transactions. Descriptive, not causal.
  - Market evidence: 3.49 USD/TORN, valued at 2024-11-25T23:58:29Z; `data/raw/tornado/requests/606a4259989db1347a6f1f24b86c.json.gz#price_index=394`.
  - Market evidence: 19.48 USD/TORN, valued at 2024-11-27T23:59:54Z; `data/raw/tornado/requests/606a4259989db1347a6f1f24b86c.json.gz#price_index=396`.
  - [0xd7b4d0041f2e9d3b447a76ff8f7fd2b2b04b092f74dd7f6f2b2ddbf2060379a2](https://etherscan.io/tx/0xd7b4d0041f2e9d3b447a76ff8f7fd2b2b04b092f74dd7f6f2b2ddbf2060379a2) (2024-11-27, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/1c1346063818c0e9f761e264.json.gz#/response/result/5465`.
  - [0x1674650ad4c24713c81b5f88f6712b574fb452ddad8345c03be58177fd92e03f](https://etherscan.io/tx/0x1674650ad4c24713c81b5f88f6712b574fb452ddad8345c03be58177fd92e03f) (2024-11-27, pool `0x910cbd523d972eb0a6f4cae4618ad62622b39dbf`); `data/raw/evm/rpc/15acf078e9968ef6738ab4c8.json.gz#/response/result/6522`.
  - [0x7964f2ec04b9fad7fb61b9f44115d9b3d2c25386bf4cad6c014913c64c2db867](https://etherscan.io/tx/0x7964f2ec04b9fad7fb61b9f44115d9b3d2c25386bf4cad6c014913c64c2db867) (2024-11-27, pool `0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936`); `data/raw/evm/rpc/dafebb985c70dc34415d3e25.json.gz#/response/result/4595`.
- **Four classic ETH pools held 309,794.3 ETH at 2026-10-22T21:58:11Z, versus 144,294.8 ETH at the paper's March 2025 endpoint block.** Confidence: High for native balances at the stated blocks. Examples illustrate contemporary pool deposits, not the complete net change. This is stock, not gross flow, seized value or legal-compliance measurement.
  - Balance evidence: `data/raw/evm/rpc/c499c66a016a7796b76d6891.json.gz`; `data/raw/evm/rpc/0a2e940a5b0feb5cc86c5805.json.gz`; `data/raw/evm/rpc/6cb60118710fbcadfccd3172.json.gz`; `data/raw/evm/rpc/8dcf178c55945654c0606c58.json.gz`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=0`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=1`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=2`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=3`.
  - [0x650311f3a8854bdd5ddbead3720d26d6cc9146fc71cbe7c8c271b2c0a8523b3a](https://etherscan.io/tx/0x650311f3a8854bdd5ddbead3720d26d6cc9146fc71cbe7c8c271b2c0a8523b3a) (2026-10-22, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/55146e0675bf985bdfc508cc.json.gz#/response/result/7860`.
  - [0x38c7d6896950a89ae0336991ea065f8dffb238e8edd062c4fe745b13310b50d3](https://etherscan.io/tx/0x38c7d6896950a89ae0336991ea065f8dffb238e8edd062c4fe745b13310b50d3) (2026-10-22, pool `0x910cbd523d972eb0a6f4cae4618ad62622b39dbf`); `data/raw/evm/rpc/97a6dd75a814d4f37e421dc0.json.gz#/response/result/4667`.
  - [0x956dfbfd35c79aadcf7f57c376fdc2a6461aa09e87b77b93ed7c9b11a5e63532](https://etherscan.io/tx/0x956dfbfd35c79aadcf7f57c376fdc2a6461aa09e87b77b93ed7c9b11a5e63532) (2026-10-22, pool `0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936`); `data/raw/evm/rpc/ebe5aeb76746f965031aec65.json.gz#/response/result/8083`.
- **The 100 ETH pool supplied 85.11% of ETH deposited in the post-delisting 30-day window; its Deposit count rose from 102 to 385.** Confidence: High for event counts and native ETH denominations. Denomination concentration does not identify people, ownership or the purpose of deposits.
  - [0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec](https://etherscan.io/tx/0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec) (2025-03-23, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/768a90a0e23a5b4cd0bfbe4b.json.gz#/response/result/1370`.
  - [0x51292e44d90ca7ee554698c4d2671ca2e5126889d8d9641b3e993235cdda5a29](https://etherscan.io/tx/0x51292e44d90ca7ee554698c4d2671ca2e5126889d8d9641b3e993235cdda5a29) (2025-03-23, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/768a90a0e23a5b4cd0bfbe4b.json.gz#/response/result/1371`.
  - [0x25e7d4d80898aa7247e65d0b1d2b796eff54ef7a8e7a04623e5289373e632f91](https://etherscan.io/tx/0x25e7d4d80898aa7247e65d0b1d2b796eff54ef7a8e7a04623e5289373e632f91) (2025-03-23, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/768a90a0e23a5b4cd0bfbe4b.json.gz#/response/result/1373`.
- **Initial OFAC designation: ETH deposits changed -67.96% in equal 30-day windows (109,626.4 → 35,125.7 ETH).** Confidence: Descriptive before/after comparison, equal UTC windows excluding event date; publication time unknown; not an estimate of causal effect. Counts cross-checked against pool nextIndex; source gaps remain explicit in coverage.
  - [0x39e477e177999a8f879ef4505c9fa8df1549b24cc5be946959b532f7632ce182](https://etherscan.io/tx/0x39e477e177999a8f879ef4505c9fa8df1549b24cc5be946959b532f7632ce182) (2022-08-09, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/3555e075d4a469d7e8863ed9.json.gz#/response/result/7250`.
  - [0x3b9f1a2628a2652408ee7f6ee2a6221e712f19bd007e1f32250bf1d87b9253e7](https://etherscan.io/tx/0x3b9f1a2628a2652408ee7f6ee2a6221e712f19bd007e1f32250bf1d87b9253e7) (2022-08-09, pool `0x910cbd523d972eb0a6f4cae4618ad62622b39dbf`); `data/raw/evm/rpc/d1f6c7cf92de96a7a4171f35.json.gz#/response/result/2821`.
  - [0x780302391733404241d454c518859fad508e09146b52b8e416fedd2c5c8b1a70](https://etherscan.io/tx/0x780302391733404241d454c518859fad508e09146b52b8e416fedd2c5c8b1a70) (2022-08-09, pool `0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936`); `data/raw/evm/rpc/0532eda0fbbc1ce02c3591d6.json.gz#/response/result/4345`.
- **Van Loon Fifth Circuit ruling: ETH deposits changed +5.06% in equal 30-day windows (27,134.1 → 28,507.2 ETH).** Confidence: Descriptive before/after comparison, equal UTC windows excluding event date; publication time unknown; not an estimate of causal effect. Counts cross-checked against pool nextIndex; source gaps remain explicit in coverage.
  - [0xd7b4d0041f2e9d3b447a76ff8f7fd2b2b04b092f74dd7f6f2b2ddbf2060379a2](https://etherscan.io/tx/0xd7b4d0041f2e9d3b447a76ff8f7fd2b2b04b092f74dd7f6f2b2ddbf2060379a2) (2024-11-27, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/1c1346063818c0e9f761e264.json.gz#/response/result/5465`.
  - [0x1674650ad4c24713c81b5f88f6712b574fb452ddad8345c03be58177fd92e03f](https://etherscan.io/tx/0x1674650ad4c24713c81b5f88f6712b574fb452ddad8345c03be58177fd92e03f) (2024-11-27, pool `0x910cbd523d972eb0a6f4cae4618ad62622b39dbf`); `data/raw/evm/rpc/15acf078e9968ef6738ab4c8.json.gz#/response/result/6522`.
  - [0x7964f2ec04b9fad7fb61b9f44115d9b3d2c25386bf4cad6c014913c64c2db867](https://etherscan.io/tx/0x7964f2ec04b9fad7fb61b9f44115d9b3d2c25386bf4cad6c014913c64c2db867) (2024-11-27, pool `0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936`); `data/raw/evm/rpc/dafebb985c70dc34415d3e25.json.gz#/response/result/4595`.
- **Withdrawal and immediate re-designation: ETH deposits changed -12.89% in equal 30-day windows (22,369.9 → 19,486.8 ETH).** Confidence: Descriptive before/after comparison, equal UTC windows excluding event date; publication time unknown; not an estimate of causal effect. Counts cross-checked against pool nextIndex; source gaps remain explicit in coverage.
  - [0xc6b3a936f824946574866fac9398752b90649080e4d321180e62202cedd050c9](https://etherscan.io/tx/0xc6b3a936f824946574866fac9398752b90649080e4d321180e62202cedd050c9) (2022-11-10, pool `0xa160cdab225685da1d56aa342ad8841c3b53f291`); `data/raw/evm/rpc/35ce4eef4247211782c046c5.json.gz#/response/result/463`.
  - [0x65ae68660db6bc39f008e16a897a68127701ca13b1c410602c8e087d6832d7ce](https://etherscan.io/tx/0x65ae68660db6bc39f008e16a897a68127701ca13b1c410602c8e087d6832d7ce) (2022-11-09, pool `0x910cbd523d972eb0a6f4cae4618ad62622b39dbf`); `data/raw/evm/rpc/a57e10631a1170418da6dec3.json.gz#/response/result/757`.
  - [0x291dd520721ba08923f076cde69f6d5dadccd647cb16519ad706fe0f997eb9a9](https://etherscan.io/tx/0x291dd520721ba08923f076cde69f6d5dadccd647cb16519ad706fe0f997eb9a9) (2022-11-09, pool `0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936`); `data/raw/evm/rpc/9b20a9a6024940228129cda7.json.gz#/response/result/835`.

### Event-window depositors

Origins are distinct top-level transaction sender addresses, not people. All observed Deposit events in the eight comparison windows have an evidenced origin. Elsewhere the daily CSV explicitly preserves missing origins.

| Event | Before, origin addresses | After, origin addresses | Before, Deposit events with known origin / all | After, Deposit events with known origin / all |
|---|---:|---:|---:|---:|
| 2022-08-08 | 2,630 | 341 | 8,110 / 8,110 | 1,463 / 1,463 |
| 2022-11-08 | 241 | 255 | 985 / 985 | 1,116 / 1,116 |
| 2024-11-26 | 240 | 285 | 1,098 / 1,098 | 1,275 / 1,275 |
| 2025-03-21 | 263 | 540 | 1,714 / 1,714 | 2,327 / 2,327 |

## Independent pool balances and comparison with arXiv 2507.11721

The paper reports 499,769.74 ETH at designation and 145,579.38 ETH at its March 2025 endpoint **across 170 addresses**, not solely Tornado. Its rounded Tornado shares (44.17% and 99.12%) imply approximately 220,748.29 ETH and 144,298.28 ETH. Those approximations are not exact published pool balances. We query the paper's explicit start/end blocks as well as the project's prior-ET-day-end checkpoint. Primary evidence and actual block times follow.

| Checkpoint | Block | Actual observation UTC | Four native-pool balance, ETH |
|---|---:|---|---:|
| designation | 15299343 | 2022-08-08T03:59:58Z | 224,186.4 (4 pools) |
| redesignation | 15923081 | 2022-11-08T04:59:59Z | 98,008.0 (4 pools) |
| van_loon | 21269694 | 2024-11-26T04:59:59Z | 159,177.4 (4 pools) |
| delisting | 22092709 | 2025-03-21T03:59:59Z | 144,227.3 (4 pools) |
| paper_start | 15302392 | 2022-08-08T15:37:47Z | 220,485.9 (4 pools) |
| paper_end | 22097863 | 2025-03-21T21:13:23Z | 144,294.8 (4 pools) |

Checkpoint raw responses (each contains the exact block and request):
- designation: block `data/raw/tornado/requests/a125af295c9f92e1a33afb553683.json.gz`; balances `data/raw/tornado/requests/4a47f6991abbdcf01140cef4c517.json.gz#response_id=0`; `data/raw/tornado/requests/4a47f6991abbdcf01140cef4c517.json.gz#response_id=1`; `data/raw/tornado/requests/4a47f6991abbdcf01140cef4c517.json.gz#response_id=2`; `data/raw/tornado/requests/4a47f6991abbdcf01140cef4c517.json.gz#response_id=3`.
- redesignation: block `data/raw/tornado/requests/70780057c0782d7119a43a9c6fcb.json.gz`; balances `data/raw/tornado/requests/1a33f14f783921ade0e66020607f.json.gz#response_id=0`; `data/raw/tornado/requests/1a33f14f783921ade0e66020607f.json.gz#response_id=1`; `data/raw/tornado/requests/1a33f14f783921ade0e66020607f.json.gz#response_id=2`; `data/raw/tornado/requests/1a33f14f783921ade0e66020607f.json.gz#response_id=3`.
- van_loon: block `data/raw/tornado/requests/2d7723ca9a9e38e704a34027f6a0.json.gz`; balances `data/raw/tornado/requests/e34e8926f1d0e51dc9195f43a910.json.gz#response_id=0`; `data/raw/tornado/requests/e34e8926f1d0e51dc9195f43a910.json.gz#response_id=1`; `data/raw/tornado/requests/e34e8926f1d0e51dc9195f43a910.json.gz#response_id=2`; `data/raw/tornado/requests/e34e8926f1d0e51dc9195f43a910.json.gz#response_id=3`.
- delisting: block `data/raw/tornado/requests/d15767109acc8539c1911d0d9c97.json.gz`; balances `data/raw/tornado/requests/fb6bb16e5c0b68b8fa803276d142.json.gz#response_id=0`; `data/raw/tornado/requests/fb6bb16e5c0b68b8fa803276d142.json.gz#response_id=1`; `data/raw/tornado/requests/fb6bb16e5c0b68b8fa803276d142.json.gz#response_id=2`; `data/raw/tornado/requests/fb6bb16e5c0b68b8fa803276d142.json.gz#response_id=3`.
- paper_start: block `data/raw/tornado/requests/36630f42eb3fce76dee01c1ca2ca.json.gz`; balances `data/raw/tornado/requests/624343eb93632e09d2e3d39100fe.json.gz#response_id=0`; `data/raw/tornado/requests/624343eb93632e09d2e3d39100fe.json.gz#response_id=1`; `data/raw/tornado/requests/624343eb93632e09d2e3d39100fe.json.gz#response_id=2`; `data/raw/tornado/requests/624343eb93632e09d2e3d39100fe.json.gz#response_id=3`.
- paper_end: block `data/raw/tornado/requests/328ef61e7258adb60ed00b5184aa.json.gz`; balances `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=0`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=1`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=2`; `data/raw/tornado/requests/d291ff820d40e114fe24ef87e10c.json.gz#response_id=3`.

At the paper's exact inclusive block window, we observe 3,489,484.4 ETH deposited before the start block and 1,011,031.6 ETH within the sanctions window: a -71.03% change in gross deposit volume, against the paper's reported −71.03%. The paper's stated 957 days counts its endpoint convention; our UTC calendar periods are half-open and put 2025-03-21 in the delisted period. The cohort and endpoint conventions must be retained when quoting either comparison.

The four-pool paper-end balance is close to, but not identical with, the balance implied by the paper's rounded Tornado share. Its 170-address balance is a different denominator. The four-pool start balance also differs from that implied share; the source does not specify an identical pool-only cohort, so this is a partial reconciliation, not an exact independent reproduction of its aggregate.

Latest common daily sample: **309,794.3 ETH**, observed at 2026-10-22T21:58:11Z. This is a direct balance observation, independent of gross flows. Its evidence: `data/raw/evm/rpc/c499c66a016a7796b76d6891.json.gz`; `data/raw/evm/rpc/0a2e940a5b0feb5cc86c5805.json.gz`; `data/raw/evm/rpc/6cb60118710fbcadfccd3172.json.gz`; `data/raw/evm/rpc/8dcf178c55945654c0606c58.json.gz`.

## Depositors, other sanctioned origins, and CEX withdrawals

The daily CSV reports distinct **observed top-level transaction origins**, not people or verified economic depositors. The known-origin denominator is explicit for every pool/day. The same origin can use several pools; window totals deduplicate it. A listed address match requires its OFAC listing date to be no later than the deposit date and precedes any recorded delisting. Tornado's own contracts are excluded from the other-sanctioned cohort. Later listings are not backdated.

A CEX-labelled origin is a direct transaction-sender label match. We have not reconstructed one-hop exchange-withdrawal funding of otherwise unlabelled depositors. Therefore the full share of deposits funded by CEX withdrawals is **unknown**, not zero. All label matches are evidence leads, not allegations about who controls the depositor or whether an exchange acted unlawfully.

| Period [start, end) | Deposit events | Origins known, events | Unique origins observed, addresses | Other-sanctioned-origin deposits, events | Other-sanctioned-origin principal, ETH | Direct CEX-labelled origin, events |
|---|---:|---:|---:|---:|---:|---:|
| 2019-12-16 – 2022-08-08 | 151,181 | 8,110 | 2,630 | 0 | 0.0 | 0 |
| 2022-08-08 – 2022-11-08 | 3,389 | 2,653 | 657 | 0 | 0.0 | 0 |
| 2022-11-08 – 2024-11-26 | 33,960 | 2,278 | 511 | 0 | 0.0 | 0 |
| 2024-11-26 – 2025-03-21 | 5,553 | 3,027 | 549 | 0 | 0.0 | 0 |
| 2025-03-21 – 2026-10-23 | 105,057 | 2,363 | 548 | 0 | 0.0 | 0 |

## TORN is a token, not pool ETH

The TORN token contract `0x77777feddddffc19ff86db637967013e6c6a116c` appears in the replacement OFAC entry (2022-11-08 → 2025-03-21). Token prices below are DefiLlama daily samples at their actual times, **not asserted exchange closing prices**. Token price changes do not measure pool TVL, transaction count, economic ownership or legal compliance.

| Legal event | Price before, USD/TORN | Price after, USD/TORN | Change |
|---|---:|---:|---:|
| designation | 30.4330 at 2022-08-07T23:59:48Z | 22.0581 at 2022-08-09T00:01:55Z | -27.52% |
| redesignation | 6.2209 at 2022-11-07T23:59:13Z | 3.4937 at 2022-11-09T23:59:52Z | -43.84% |
| van_loon | 3.4900 at 2024-11-25T23:58:29Z | 19.4800 at 2024-11-27T23:59:54Z | +458.17% |
| delisting | 8.3600 at 2025-03-20T23:59:55Z | 11.8400 at 2025-03-22T23:58:47Z | +41.63% |

## Same address, other chain

The current ledger assigns every Tornado identifier to ETH. The pinned Tornado deployment configuration separately identifies BSC, Polygon, Arbitrum and Optimism pools. The identical address string can have a different denomination or asset on another chain. Their native balances below are **never summed with ETH mainnet**. Ordinary account-history rows are not relabelled as pool events; complete Deposit/Withdrawal series on these chains remain a gap.

| Chain | Pool | Deployment label | Native balance, native units | Balance block | History complete |
|---|---|---|---:|---:|---|
| arb | `0x1e34a77868e19a6647b1f2f47b51ed72dede95dd` | Tornado Cash: 100 eth pool | 0 ETH | 517494287 | True |
| arb | `0x330bdfade01ee9bf63c209ee33102dd334618e0a` | Tornado Cash: 10 eth pool | 60 ETH | 517494287 | True |
| arb | `0x84443cfd09a48af6ef360c6976c5392ac5023a1f` | Tornado Cash: 0.1 eth pool | 27.1 ETH | 517494287 | True |
| arb | `0xd47438c816c9e7f2e2888e060936a499af9582b3` | Tornado Cash: 1 eth pool | 142 ETH | 517494287 | True |
| bsc | `0x1e34a77868e19a6647b1f2f47b51ed72dede95dd` | Tornado Cash: 100 bnb pool | 68100 BNB | 129294085 | False |
| bsc | `0x330bdfade01ee9bf63c209ee33102dd334618e0a` | Tornado Cash: 10 bnb pool | 7130 BNB | 129294085 | False |
| bsc | `0x84443cfd09a48af6ef360c6976c5392ac5023a1f` | Tornado Cash: 0.1 bnb pool | 500 BNB | 129294085 | False |
| bsc | `0xd47438c816c9e7f2e2888e060936a499af9582b3` | Tornado Cash: 1 bnb pool | 2060 BNB | 129294442 | False |
| op | `0x1e34a77868e19a6647b1f2f47b51ed72dede95dd` | Tornado Cash: 100 eth pool | 0 ETH | 158571487 | True |
| op | `0x330bdfade01ee9bf63c209ee33102dd334618e0a` | Tornado Cash: 10 eth pool | 0 ETH | 158572813 | True |
| op | `0x84443cfd09a48af6ef360c6976c5392ac5023a1f` | Tornado Cash: 0.1 eth pool | 6.5 ETH | 158572813 | True |
| op | `0xd47438c816c9e7f2e2888e060936a499af9582b3` | Tornado Cash: 1 eth pool | 5 ETH | 158572813 | True |
| polygon | `0x1e34a77868e19a6647b1f2f47b51ed72dede95dd` | Tornado Cash: 100 matic pool | 58200 POL | 96028493 | True |
| polygon | `0xa5c2254e4253490c54cef0a4347fddb8f75a4998` | Tornado Cash: 100000 matic pool | 0 POL | 96028493 | True |
| polygon | `0xaf4c0b70b2ea9fb7487c7cbb37ada259579fe040` | Tornado Cash: 10000 matic pool | 210000 POL | 96028493 | True |
| polygon | `0xdf231d99ff8b6c6cbf4e9b9a945cbacef9339178` | Tornado Cash: 1000 matic pool | 173000 POL | 96024026 | True |

## Coverage, reproducibility and confidence

- All Tornado ledger entries use ETH in the current ledger; BSC/Polygon/Arbitrum/OP deployment activity is separate same-address/other-chain evidence, not an additional OFAC chain designation.
- Unique depositors means distinct evidenced top-level transaction origins, a lower bound on origin addresses and never a count of people. Contract callers and economic depositors can differ.
- CEX-labelled origin is a direct transaction-origin label match only. One-hop CEX withdrawal funding of unlabelled depositors is unmeasured; unknown origins and unlabelled senders are not clean funds.
- Pool TVL samples retain their actual observation time. USD at day close revalues that sample, not an independently observed closing balance.
- Daily missing/unreadable inputs are not zero activity. Full log coverage and date assignment are separately reported.
- `--check` uses the pinned, compressed input snapshot; it recomputes JSON and daily CSV and compares exact outputs. A normal rerun reads the newest available timelines and replaces the provisional snapshot. Shared source files are never edited.
- Missing timeline files, malformed gzip/JSON, and partial schemas are counted individually. Pool-event gaps and unresolved withdrawal dates remain visible. No missing observation becomes a zero balance.
- Deposit dates come from events; withdrawal UTC dates can also be proved by bounding block timestamps. Such a date is exact even when its intraday time remains unknown. Bounds and exact source references are preserved in the pinned snapshot.
- Native-principal events exclude unrelated tokens, unsolicited transfers and administration calls. DAI/USDT/USDC pool units remain separate; cDAI/cUSDC and WBTC are not automatically valued using a different token's price.
- Before/after windows can be affected by market conditions, exploits, service substitution and simultaneous news. November 2022 is a withdrawal and immediate re-designation, not an ordinary unsanctioned interval. The Fifth Circuit ruling is a distinct legal milestone from OFAC's March 2025 removal.


Research, not legal or compliance advice. Labels are leads. A factual on-chain receipt does not establish wrongdoing.
