# Inflows after designation — completed bounded snapshot

Snapshot: **2026-10-23T21:03:34Z**. **1,147 / 1,148 ledger chain-address pairs** have readable timelines; **1,095** have provider-complete scoped histories. Ledger trackability is reported separately. Data as of 2026-10-23; bounded acquisition is complete and source-specific history gaps remain. These are observations within data checked, not whole-project totals.

Non-Tornado addresses received **329 real asset-transfer events**, worth **$2,905,356.06 at transfer time** while listed. This is summed turnover, not unique money or customer payments. The records identify **374 funding/sender addresses**, not people; **1** real events have no identified direct sender.

Excluded from that real-event total: **26,208 dust events**, **1,706 operational poisoning/spam events**, and **1 recognised-asset events without a price**. Off-list-token spam classification is low confidence and may exclude legitimate tokens.

## Reproduce and refresh

```sh
.venv/bin/python -B scripts/analysis/inflows.py
.venv/bin/python -B scripts/analysis/inflows.py --check
.venv/bin/python -B scripts/analysis/inflows.py --self-test
```

The first command atomically replaces the analysis CSV, JSON and write-up. It works on whichever saved files exist. `--check` verifies input digests, recomputes the saved timeline path set and compares all three outputs. New files are ignored during that check; an overwritten ledger timeline or other relevant changed input causes an explicit failure and calls for refresh. Missing/truncated candidate ledger JSON or gzip files are counted and skipped; other-chain filenames are counted as outside scope. Machine-readable table rows carry `raw_ref` files and USD aggregates also carry price raw files; exact event pointers and request provenance are in the CSV and saved raw envelopes. No API calls, key reads, installs or shared-file writes occur.

## Candidate findings

### Largest observed wallet receipts

**SEMENOV, Roman** — `ETH:0xed6e0a7e4ac94d976eebfb82ccf777a3c6bad921` (listed 2023-08-23).
Observed **2 real events**, **$1,341,680.82 at transfer time**, and **2 distinct known funding/sender addresses**. 0 events lack an identified sender. Latest receipt: 2023-11-27T02:43:11Z (**95.95 days** after T).
Pattern: `one_time_large_or_dominant`. Largest event **$1,341,519.11**, **100.0%** of observed value; **2 active months**, longest consecutive run **1 months**; median event **$670,840.41**. Amounts use each transfer's historical observation, not current prices.
Two years or more after T: **0 real events**, **$0.00 at those transfer times**.
Confidence: High confidence in saved recognised-asset transfer arithmetic; provisional history and label coverage. Motive, beneficial ownership and number of people are not inferred. Positive net receipts on UTXO chains can include own-fund consolidation. Off-list tokens and unpriced recognised assets excluded. Timeline complete flag: `True`; exchange-scale flag: `False`.

**Attribution caveat:** **1 events / $1,341,519.11 at transfer time** came from addresses sharing the recipient's OFAC UID. These are transfers between addresses listed under the same name, not evidence of outside payments.

- [0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73](https://etherscan.io/tx/0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73) — 2023-11-27T02:43:11Z; 650 ETH; $1,341,519.11, price observed 2023-11-27T02:00:00Z; raw `data/raw/evm/etherscan/e50db83fbf6fcb8b69607a0b.json.gz#/response/result/49`; price raw `data/raw/prices/binance/ETH-1H/9b6f2bf84fc04018a5a7a2d189ff457216525a00cb78400f8467d89b9aa3088d.json.gz#row=624;data/raw/prices/binance/USDT-HOURLY-FX-1H/34c55591112799b87b94b7605bebcdeb12d75229718628b7f45b77c5e31a754b.json.gz#row=336`.
- [0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32](https://etherscan.io/tx/0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32) — 2023-08-24T16:11:59Z; 0.0984395508239755 ETH; $161.71, price observed 2023-08-24T16:00:00Z; raw `data/raw/evm/etherscan/3d9dd1d54e3a3425194382f8.json.gz#/response/result/60`; price raw `data/raw/prices/binance/ETH-1H/f4640feaded8811519dcd74eb541cbea48292cd0bd50028045797d07a459de91.json.gz#row=358;data/raw/prices/binance/USDT-HOURLY-FX-1H/8e21c2778773cb5fcce1b9e2446f02b0abf9194beff8a5ca1d2c7a892e248172.json.gz#row=70`.

Raw example checks: `0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73`: verified_hash_amount_recipient; `0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32`: verified_hash_amount_recipient.

### Receipts years after designation

**SECONDEYE SOLUTION** — `ETH:0x1da5821544e25c636c1417ba96ade4cf6d2f9b5a` (listed 2021-04-15).
Observed **2 real events**, **$3.84 at transfer time**, and **1 distinct known funding/sender addresses**. 0 events lack an identified sender. Latest receipt: 2026-08-19T09:30:47Z (**1,952.23 days** after T).
Pattern: `recurring_or_mixed`. Largest event **$1.92**, **50.0%** of observed value; **1 active months**, longest consecutive run **1 months**; median event **$1.92**. Amounts use each transfer's historical observation, not current prices.
Two years or more after T: **2 real events**, **$3.84 at those transfer times**.
Confidence: High confidence in saved recognised-asset transfer arithmetic; provisional history and label coverage. Motive, beneficial ownership and number of people are not inferred. Positive net receipts on UTXO chains can include own-fund consolidation. Off-list tokens and unpriced recognised assets excluded. Timeline complete flag: `True`; exchange-scale flag: `False`.

- [0xf0df2f4d1d17bab30d3c16cc12b0b37a507fb32a916649c3550f9250f97d1cb6](https://etherscan.io/tx/0xf0df2f4d1d17bab30d3c16cc12b0b37a507fb32a916649c3550f9250f97d1cb6) — 2026-08-19T09:30:47Z; 0.001 ETH; $1.92, price observed 2026-08-19T09:00:00Z; raw `data/raw/evm/etherscan/f4c62957d25cb844679c5b0e.json.gz#/response/result/72`; price raw `data/raw/prices/binance/ETH-1H/f5317eb6dfeeaa20afcd47c5ebddcc76160a99508b6bd4b3af4599a18e8d3e81.json.gz#row=535;data/raw/prices/binance/USDT-HOURLY-FX-1H/c10c7ef251905ba412f9aeef20124c9a18628042138e00fc1663e5350128179d.json.gz#row=247`.
- [0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f](https://etherscan.io/tx/0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f) — 2026-08-19T09:29:23Z; 0.001 ETH; $1.92, price observed 2026-08-19T09:00:00Z; raw `data/raw/evm/etherscan/f4c62957d25cb844679c5b0e.json.gz#/response/result/71`; price raw `data/raw/prices/binance/ETH-1H/f5317eb6dfeeaa20afcd47c5ebddcc76160a99508b6bd4b3af4599a18e8d3e81.json.gz#row=535;data/raw/prices/binance/USDT-HOURLY-FX-1H/c10c7ef251905ba412f9aeef20124c9a18628042138e00fc1663e5350128179d.json.gz#row=247`.

Raw example checks: `0xf0df2f4d1d17bab30d3c16cc12b0b37a507fb32a916649c3550f9250f97d1cb6`: verified_hash_amount_recipient; `0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f`: verified_hash_amount_recipient.

### Steady drips

**AL-LAW, Tawfiq Muhammad Sa'id** — `TRX:TWBAPzpPiZarfVsY2BLXeaLhNHurn4wkWG` (listed 2024-03-26).
Observed **42 real events**, **$419.34 at transfer time**, and **11 distinct known funding/sender addresses**. 0 events lack an identified sender. Latest receipt: 2026-09-08T01:45:09Z (**895.91 days** after T).
Pattern: `steady_drips`. Largest event **$66.32**, **15.8%** of observed value; **11 active months**, longest consecutive run **4 months**; median event **$5.57**. Amounts use each transfer's historical observation, not current prices.
Two years or more after T: **22 real events**, **$165.10 at those transfer times**.
Confidence: High confidence in saved recognised-asset transfer arithmetic; provisional history and label coverage. Motive, beneficial ownership and number of people are not inferred. Positive net receipts on UTXO chains can include own-fund consolidation. Off-list tokens and unpriced recognised assets excluded. Timeline complete flag: `True`; exchange-scale flag: `False`.

- [faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06](https://tronscan.org/#/transaction/faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06) — 2025-03-12T16:45:03Z; 300 TRX; $66.32, price observed 2025-03-12T16:00:00Z; raw `data/raw/tron/native/d417c27b9007ecf1e0b758674bef24089d1bcf885e09f1bee07b47c9ed0695cd.json.gz#/response/data/164`; price raw `data/raw/prices/binance/TRX-1H/4266f2f7492151244854599551a52651d6d34ef88726248e4746584e8147d294.json.gz#row=101;data/raw/prices/binance/USDT-HOURLY-FX-1H/13ea76c3959491ed852e30979d02b9c10ad894a2109c946b6f0ed5e2b83fe716.json.gz#row=654`.
- [0a0f157ac582a4efab66516d890bff71d09d7ecf929519e02f239f2b1b29752c](https://tronscan.org/#/transaction/0a0f157ac582a4efab66516d890bff71d09d7ecf929519e02f239f2b1b29752c) — 2026-09-02T03:40:48Z; 150 TRX; $48.28, price observed 2026-09-02T03:00:00Z; raw `data/raw/tron/native/fe4631753d8e0e772cac874fe2700fd6d7340aa7756d96b6c8bb59a2511a7c85.json.gz#/response/data/33`; price raw `data/raw/prices/binance/TRX-1H/0ebeea8860a75d7c679d6a0add2a4338a5f14852c52ede803406f3fea3e91484.json.gz#row=24;data/raw/prices/binance/USDT-HOURLY-FX-1H/c10c7ef251905ba412f9aeef20124c9a18628042138e00fc1663e5350128179d.json.gz#row=577`.
- [4cb848585f235d4de98443cc6d89aa20ad54c34d5e2130a2dfe30564fb0cf37c](https://tronscan.org/#/transaction/4cb848585f235d4de98443cc6d89aa20ad54c34d5e2130a2dfe30564fb0cf37c) — 2025-02-11T14:08:33Z; 180 TRX; $44.05, price observed 2025-02-11T14:00:00Z; raw `data/raw/tron/native/d417c27b9007ecf1e0b758674bef24089d1bcf885e09f1bee07b47c9ed0695cd.json.gz#/response/data/110`; price raw `data/raw/prices/binance/TRX-1H/379eaedfdbabe2f8b812fe1ccf6de84fcc1684dfc6671fcb3372b8b1eaf40c0b.json.gz#row=403;data/raw/prices/binance/USDT-HOURLY-FX-1H/6a97f5a8e66c1a04ab464053e85e388c8d95d8321162f4eef198f1232e1a8bf0.json.gz#row=956`.

Raw example checks: `faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06`: verified_hash_amount_recipient; `0a0f157ac582a4efab66516d890bff71d09d7ecf929519e02f239f2b1b29752c`: verified_hash_amount_recipient; `4cb848585f235d4de98443cc6d89aa20ad54c34d5e2130a2dfe30564fb0cf37c`: verified_hash_amount_recipient.

### Repeated receipts from one sender

**CHATEX** — `ETH:0x48549a34ae37b12f6a30566245176994e17c6b4a` (listed 2021-11-08).
Observed **11 real events**, **$93,688.48 at transfer time**, and **1 distinct known funding/sender addresses**. 0 events lack an identified sender. Latest receipt: 2022-01-03T18:13:53Z (**56.55 days** after T).
Pattern: `recurring_or_mixed`. Largest event **$26,755.35**, **28.6%** of observed value; **3 active months**, longest consecutive run **3 months**; median event **$6,760.70**. Amounts use each transfer's historical observation, not current prices.
Two years or more after T: **0 real events**, **$0.00 at those transfer times**.
Confidence: High confidence in saved recognised-asset transfer arithmetic; provisional history and label coverage. Motive, beneficial ownership and number of people are not inferred. Positive net receipts on UTXO chains can include own-fund consolidation. Off-list tokens and unpriced recognised assets excluded. Timeline complete flag: `True`; exchange-scale flag: `False`.

- [0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000](https://etherscan.io/tx/0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000) — 2021-12-30T16:28:29Z; 26750 0xdac17f958d2ee523a2206206994597c13d831ec7; $26,755.35, price observed 2021-12-30T16:00:00Z; raw `data/raw/evm/etherscan/261226a12b77f3a7ba615e4e.json.gz#/response/result/76`; price raw `data/raw/prices/binance/USDT-HOURLY-FX-1H/b36d7a7a3b0b9a6aabeaf0c8d3afef6be14ab3c48d9443a74c0c861fc46f8572.json.gz#row=618`.
- [0xe24d780ddf5970c9de51f478483ce2dcc2f5493fb4f55b12ba7969d9638f1e6e](https://etherscan.io/tx/0xe24d780ddf5970c9de51f478483ce2dcc2f5493fb4f55b12ba7969d9638f1e6e) — 2021-11-10T11:38:55Z; 3.22209686 ETH; $15,276.31, price observed 2021-11-10T11:00:00Z; raw `data/raw/evm/etherscan/95ac3657eaeefe49ab77d6cc.json.gz#/response/result/466`; price raw `data/raw/prices/binance/ETH-1H/17f66629eabb420606a15228ccec22f20062923975f94cff6e3e852c8661654a.json.gz#row=706;data/raw/prices/binance/USDT-HOURLY-FX-1H/25e65299f9f3f75a40e38b9b08db50601b93326e21c5dc748512844aa6dd23c6.json.gz#row=413`.
- [0x1d765527e5f6538e3b8bdbf2b1e29c3f8f9f8e70572e71d37a931ffe7e5c2311](https://etherscan.io/tx/0x1d765527e5f6538e3b8bdbf2b1e29c3f8f9f8e70572e71d37a931ffe7e5c2311) — 2021-11-08T09:15:29Z; 2.15576306 ETH; $10,223.97, price observed 2021-11-08T09:00:00Z; raw `data/raw/evm/etherscan/95ac3657eaeefe49ab77d6cc.json.gz#/response/result/464`; price raw `data/raw/prices/binance/ETH-1H/17f66629eabb420606a15228ccec22f20062923975f94cff6e3e852c8661654a.json.gz#row=656;data/raw/prices/binance/USDT-HOURLY-FX-1H/25e65299f9f3f75a40e38b9b08db50601b93326e21c5dc748512844aa6dd23c6.json.gz#row=363`.

Raw example checks: `0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000`: verified_hash_amount_recipient; `0xe24d780ddf5970c9de51f478483ce2dcc2f5493fb4f55b12ba7969d9638f1e6e`: verified_hash_amount_recipient; `0x1d765527e5f6538e3b8bdbf2b1e29c3f8f9f8e70572e71d37a931ffe7e5c2311`: verified_hash_amount_recipient.

## Scope and sensitivity

Without exchange-scale addresses: **306 real events**, **$2,901,486.19 at transfer time**. Scale is >10,000 observed distinct transaction hashes or provider-reported history; incomplete histories may conceal scale.
Complete-history timelines only: **328 real events**, **$2,905,353.86 at transfer time**.
Excluding senders that share the recipient's OFAC UID leaves **323 real events / $1,563,645.74 at transfer time**. The remainder is not necessarily external customer funding; unlabelled addresses can also be related.
Designation-date sensitivity: **57 real events** fall on T's ET calendar date, whose intraday publication time is unknown. Excluding that entire day leaves **$1,889,322.96 at transfer time**.

An event is an asset transfer, not a transaction. Several events can share one transaction hash. UTXO histories supply positive net address receipts rather than gross output receipts; change and self-funding cannot be inferred away. Incoming sender counts use input addresses only, never other outputs. Tornado's entire listed address cohort is separated conservatively, including role-unresolved administrative addresses. Same-string activity on non-listed EVM chains is excluded.

## Chain coverage

| Chain | Ledger addresses | Timeline addresses | Complete history | Untrackable |
|---|---:|---:|---:|---:|
| ARB | 1 | 1 | 1 | 0 |
| BCH | 7 | 7 | 7 | 0 |
| BNB | 1 | 1 | 0 | 0 |
| BSC | 1 | 1 | 0 | 0 |
| BSV | 1 | 1 | 1 | 0 |
| BTC | 535 | 535 | 535 | 0 |
| BTG | 1 | 1 | 1 | 1 |
| DASH | 5 | 5 | 5 | 0 |
| DOGE | 2 | 2 | 2 | 0 |
| ETC | 1 | 1 | 1 | 0 |
| ETH | 217 | 216 | 188 | 1 |
| LTC | 13 | 13 | 13 | 0 |
| SOL | 4 | 4 | 0 | 0 |
| TRX | 341 | 341 | 340 | 0 |
| XMR | 12 | 12 | 0 | 12 |
| XRP | 1 | 1 | 1 | 0 |
| XVG | 1 | 1 | 0 | 0 |
| ZEC | 4 | 4 | 0 | 0 |

Per-chain status, source notes, missing files and explicit skip counts (including zero) are under `coverage` in `results/inflows.json`. Additional source-specific limits are linked from `docs/COVERAGE.md`. `docs/sources/UTXO.md` reports a working BTG history despite the earlier ledger's untrackable flag; both fields are preserved, with provider completeness controlling coverage. Native-UTXO completeness does not cover Omni, CashTokens/SLP or shielded flows. Missing ZEC/XVG routes and Monero privacy limits do not establish inactivity. `docs/sources/TRON.md` distinguishes exhausted paging from balance reconciliation and notes unresolved multiplicity for identical TRC-20 logs without log indexes. A complete history flag here is not independent financial reconciliation; these are observed events, with that source limitation retained.

## Programs and receipts years later

Program memberships overlap: do not sum program rows. These are native receipts; no donation, ransomware-payment or payroll motive is established from a transfer alone.

| Program | Real events while listed | USD at transfer time | Receiving addresses | Real events ≥2 years later |
|---|---:|---:|---:|---:|
| DPRK3 | 16 | $1,547,587.91 | 7 | 6 |
| CYBER2 | 148 | $513,810.30 | 32 | 13 |
| SDGT | 103 | $429,225.83 | 32 | 24 |
| IFSR | 9 | $416,475.73 | 7 | 0 |
| CYBER4 | 30 | $401,589.95 | 7 | 0 |
| RUSSIA-EO14024 | 10 | $359,903.79 | 4 | 0 |
| FTO | 44 | $11,784.28 | 17 | 0 |
| TCO | 8 | $8,177.12 | 7 | 0 |
| ELECTION-EO13848 | 50 | $3,179.59 | 8 | 6 |
| ILLICIT-DRUGS-EO14059 | 5 | $3,051.70 | 5 | 0 |
| NPWMD | 29 | $1,711.24 | 4 | 1 |
| IRAN | 2 | $151.50 | 2 | 0 |
| IRGC | 2 | $151.50 | 2 | 0 |
| SDNTK | 13 | $124.30 | 11 | 2 |
| IRAN-EO13902 | 1 | $3.29 | 1 | 0 |
| CAATSA - RUSSIA | 0 | $0.00 | 0 | 0 |
| CYBER3 | 0 | $0.00 | 0 | 0 |
| DPRK4 | 0 | $0.00 | 0 | 0 |
| HRIT-IR | 0 | $0.00 | 0 | 0 |

### Targeted leads: Tron SDGT, DPRK and named ransomware cases

- LAZARUS GROUP, `ETH:0x098b716b8aaf21512996dc57eb0615e2383e2f96`: **8 real events / $176,671.54 at transfer time**; **2** events ≥2 years after listing; latest 2026-10-01T13:34:11Z; one_time_large_or_dominant; timeline complete `True`. Example: [0x202a67d3a1d52e4dd5e1eebe49da511164b6e4a1ebe717dcf4674dd83a2bd457](https://etherscan.io/tx/0x202a67d3a1d52e4dd5e1eebe49da511164b6e4a1ebe717dcf4674dd83a2bd457). Full evidence is in `address_rankings`.
- SEMENOV, Roman, `ETH:0xdcbeffbecce100cce9e4b153c4e15cb885643193`: **1 real events / $29,218.96 at transfer time**; **1** events ≥2 years after listing; latest 2026-10-15T13:47:23Z; one_time_large_or_dominant; timeline complete `True`. Example: [0x7232c1e53988a63bd527873872602dc351ea06d71aa60038c477f2096be86455](https://etherscan.io/tx/0x7232c1e53988a63bd527873872602dc351ea06d71aa60038c477f2096be86455). Full evidence is in `address_rankings`.
- AL-LAW, Tawfiq Muhammad Sa'id, `TRX:TWBAPzpPiZarfVsY2BLXeaLhNHurn4wkWG`: **42 real events / $419.34 at transfer time**; **22** events ≥2 years after listing; latest 2026-09-08T01:45:09Z; steady_drips; timeline complete `True`. Example: [faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06](https://tronscan.org/#/transaction/faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06). Full evidence is in `address_rankings`.
- HYDRA MARKET, `BTC:3K4rjdh8A5yi6LWvft2rbmyZvqEbPSSSX4`: **1 real events / $22.07 at transfer time**; **1** events ≥2 years after listing; latest 2025-09-11T15:41:23Z; one_time_large_or_dominant; timeline complete `True`. Example: [721b8efa2d45c789d5c73596bd3a1472c8e2a5231ba45ae2b23926935f980af8](https://mempool.space/tx/721b8efa2d45c789d5c73596bd3a1472c8e2a5231ba45ae2b23926935f980af8). Full evidence is in `address_rankings`.
- KHORASHADIZADEH, Ali, `BTC:149w62rY42aZBox8fGcmqNsXUzSStKeq8C`: **3 real events / $13.62 at transfer time**; **1** events ≥2 years after listing; latest 2024-09-13T18:51:26Z; recurring_or_mixed; timeline complete `True`. Example: [e8a3c56dfd228dd0dc5c27d077709caafbfe76a455d4f61392a7c2a38e76e5a8](https://mempool.space/tx/e8a3c56dfd228dd0dc5c27d077709caafbfe76a455d4f61392a7c2a38e76e5a8). Full evidence is in `address_rankings`.
- SUEX OTC, S.R.O., `BTC:1ECeZBxCVJ8Wm2JSN3Cyc6rge2gnvD3W5K`: **2 real events / $10.75 at transfer time**; **1** events ≥2 years after listing; latest 2023-09-21T15:25:56Z; recurring_or_mixed; timeline complete `True`. Example: [a1c24b60b46ec1175ebf6fb1f6187de514ac2c88b00dd27b7421ed6faa59b9c6](https://mempool.space/tx/a1c24b60b46ec1175ebf6fb1f6187de514ac2c88b00dd27b7421ed6faa59b9c6). Full evidence is in `address_rankings`.
- SUEX OTC, S.R.O., `ETH:0x2f389ce8bd8ff92de3402ffce4691d17fc4f6535`: **2 real events / $6.37 at transfer time**; **2** events ≥2 years after listing; latest 2023-11-06T20:39:35Z; recurring_or_mixed; timeline complete `True`. Example: [0xde571d06217f7269f40e04a0c4bbe2fa302b3329dde4f633e8569cfb29f98d3c](https://etherscan.io/tx/0xde571d06217f7269f40e04a0c4bbe2fa302b3329dde4f633e8569cfb29f98d3c). Full evidence is in `address_rankings`.
- LAZARUS GROUP, `ETH:0xa0e1c89ef1a489c9c7de96311ed5ce5d32c20e4b`: **2 real events / $6.16 at transfer time**; **2** events ≥2 years after listing; latest 2024-12-24T14:33:23Z; recurring_or_mixed; timeline complete `True`. Example: [0x3dd3d1f95cb3921c9b59d9682159853756cf9841bfde16b0938348cd1fd5b43e](https://etherscan.io/tx/0x3dd3d1f95cb3921c9b59d9682159853756cf9841bfde16b0938348cd1fd5b43e). Full evidence is in `address_rankings`.
- TIAN, Yinyin, `BTC:15YK647qtoZQDzNrvY6HJL6QwXduLHfT28`: **1 real events / $1.22 at transfer time**; **1** events ≥2 years after listing; latest 2023-02-16T15:43:34Z; one_time_large_or_dominant; timeline complete `True`. Example: [bf2a0d3816c23f4f218df1314bf7521e34cb77d8484d8c5af41c5ab77926af26](https://mempool.space/tx/bf2a0d3816c23f4f218df1314bf7521e34cb77d8484d8c5af41c5ab77926af26). Full evidence is in `address_rankings`.
- SEMENOV, Roman, `ETH:0xed6e0a7e4ac94d976eebfb82ccf777a3c6bad921`: **2 real events / $1,341,680.82 at transfer time**; **0** events ≥2 years after listing; latest 2023-11-27T02:43:11Z; one_time_large_or_dominant; timeline complete `True`. Example: [0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73](https://etherscan.io/tx/0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73). Full evidence is in `address_rankings`.
- DERAKHSHAN, Alireza, `TRX:TSxAAo67VTDgKT537EVXxdogkJtk9c6ojz`: **3 real events / $416,268.32 at transfer time**; **0** events ≥2 years after listing; latest 2025-09-16T10:18:00Z; recurring_or_mixed; timeline complete `True`. Example: [c7fe2435fae517c91fe38b1197ac7b424d7a747c6db3a08f1e4e24c1b6c50bca](https://tronscan.org/#/transaction/c7fe2435fae517c91fe38b1197ac7b424d7a747c6db3a08f1e4e24c1b6c50bca). Full evidence is in `address_rankings`.
- SUEX OTC, S.R.O., `BTC:1B64QRxfaa35MVkf7sDjuGUYAP5izQt7Qi`: **3 real events / $274,805.00 at transfer time**; **0** events ≥2 years after listing; latest 2021-09-22T16:57:50Z; recurring_or_mixed; timeline complete `True`. Example: [734a6cab64fd470eb8142f530ecddfb5391840d18d577c273844a3219931bf8e](https://mempool.space/tx/734a6cab64fd470eb8142f530ecddfb5391840d18d577c273844a3219931bf8e). Full evidence is in `address_rankings`.

## Sender label classes

| Sender class | Real events | USD at transfer time |
|---|---:|---:|
| unlabelled | 309 | $1,450,646.62 |
| same_listed_entity | 6 | $1,341,710.31 |
| unknown_service | 9 | $95,855.04 |
| dex | 4 | $17,137.66 |
| unidentified_sender | 1 | $6.43 |

A labelled hot-wallet sender is a CEX withdrawal lead. It does not identify the customer or establish legal responsibility. Deposit-labelled senders retain their separate role; conflicting labels stay ambiguous. Other-sanctioned classification uses designation/delisting dates at transfer time. Shared OFAC UIDs are marked `same_listed_entity`. Undated public service labels may not have been valid historically. Missing labels mean unlabelled, not private persons.

## Timing curve

| Days after T (inclusive / exclusive) | Real events | USD at transfer time | Addresses old enough in checked data |
|---|---:|---:|---:|
| 0–1 | 57 | $1,016,033.10 | 1053 |
| 1–7 | 43 | $159,056.30 | 1053 |
| 7–30 | 29 | $54,791.42 | 1053 |
| 30–90 | 57 | $95,673.57 | 1046 |
| 90–365 | 65 | $1,544,059.67 | 948 |
| 365–730 | 34 | $6,145.39 | 658 |
| 730–1095 | 34 | $320.80 | 555 |
| 1095–latest | 10 | $29,275.81 | 470 |

These age bins are a descriptive timing curve. Different designation cohorts, incomplete acquisition, unequal bin widths and unequal time exposed prevent interpreting the raw decline as a sanctions effect. Complete-history eligibility counts are retained in JSON.

## Tornado analysis: wallet side

- Direct transfers from other listed addresses to the Tornado cohort: **0 events / $0.00** during Tornado sanctions; **0 events / $0.00** after Tornado delisting. All USD is valued at each transfer time.

The Tornado analysis covers contract-specific deposit analysis, matched-window comparisons and delisting interpretation (`results/tornado.json`, `docs/analysis/TORNADO.md`). This output includes `tornado_wallet_side.transfer_evidence`. Tornado timelines are read to count availability, but their incoming events are covered by that separate analysis. Pool logs without sender information cannot establish unique wallet depositors. Summing router and pool receipts would double-count routed funds.


## Why the filter matters

**98.83% of observed during-sanctions incoming records** are dust or operational spam under these rules; **20,956** are zero-value records without a demonstrated mimic. This share is about records, not people or transferred value. **13** records meet the prior-counterparty address-mimic rule. Confidence: Recorded zero/low value is factual; a matching address pattern or missing token-list entry does not establish intent. These records are not all payments.

- Mimic-rule example: [0x0a094420b6ffe21698776a4dc5a2566c6d82ff8efcb9576016b5061ae4a53c60](https://etherscan.io/tx/0x0a094420b6ffe21698776a4dc5a2566c6d82ff8efcb9576016b5061ae4a53c60) — 2026-07-27T11:11:47Z; 0.000011 ETH; raw `data/raw/evm/etherscan/e89c4bb956b6d333ee51d5a3.json.gz#/response/result/37`. Exact matching counterparty is recorded in the CSV.
- Mimic-rule example: [0xd33ef30ec1599aa18e14db9de153659d01c336c6e828eaadc559d62d8c793480](https://etherscan.io/tx/0xd33ef30ec1599aa18e14db9de153659d01c336c6e828eaadc559d62d8c793480) — 2026-07-27T11:08:35Z; 0.000011 ETH; raw `data/raw/evm/etherscan/3d9dd1d54e3a3425194382f8.json.gz#/response/result/63`. Exact matching counterparty is recorded in the CSV.
- Mimic-rule example: [0x1b25e6ad8a3344a18a23cffeda2759e8e7d7848115d7196045a5cff0ad2c77fa](https://etherscan.io/tx/0x1b25e6ad8a3344a18a23cffeda2759e8e7d7848115d7196045a5cff0ad2c77fa) — 2026-07-27T10:14:47Z; 0.000011 ETH; raw `data/raw/evm/etherscan/f53be75d9098b9a5223f883c.json.gz#/response/result/429`. Exact matching counterparty is recorded in the CSV.
- **Unpriced and excluded from real/dust totals:** 159912.472222222222222223 0x77777feddddffc19ff86db637967013e6c6a116c to `0x5a7a51bfb49f190e5a6060a5bc6052ac14a3b59f` on 2023-12-06T16:06:11Z; [0x7a5b916a2e88bea98f41c225c7378aadf0fbe2e5c3fc8064b724d059a0ae5022](https://etherscan.io/tx/0x7a5b916a2e88bea98f41c225c7378aadf0fbe2e5c3fc8064b724d059a0ae5022); raw `data/raw/evm/etherscan/573ce30eddebc8607550fcfc.json.gz#/response/result/43`. This can be economically material; no USD is invented.

## Classification, valuation and limits

Every usable post-T incoming row carries its rule in `data/derived/inflows.csv`. Native asset/recognised contract receipts ≥$1 are real; <$1 are dust. A sender matching both the first and last four characters of a different, prior real outgoing counterparty is marked poisoning only for zero/<$1 receipts. Zero without a demonstrated mimic stays dust. Tokens outside the explicit list in the script/JSON enter the poisoning/spam bucket with low confidence; this is an operational token-list rule, not proof of intent. The rule is deliberately visible so a broader reviewed token list can change the classification.
Positive recognised-asset events without a saved price remain unresolved with an empty `inflow_class`. This is an explicit exception proposed to the three-class requirement: fabricating a USD threshold would violate the price/evidence rules. `unclassified_price_events` counts them; no unavailable price is replaced with zero or $1. Stablecoins use saved historical quotes. WETH uses an explicit ETH price proxy; WBTC and other assets without a configured price are not silently valued as their underlying.
USD figures are the sum of per-event valuations using `scripts/prices/price.py usd()`: latest saved hourly observation at/before the transfer if at most two hours old, otherwise daily at most two days old. Each row records the actual observation time, quote, source URL and raw response. Figures are estimates at the available observation frequency, not exact executable prices. Addresses, asset events, transactions, programs and people remain different units.
No inference identifies the controller of an unlabelled address or a sender's motive. Receiving funds does not establish a legal violation. Research, not legal or compliance advice.

Prior-art distinction: this listed-address-only, evidence-linked cross-chain analysis separates dust/spam, net UTXO receipts, sender-label uncertainty and persistent post-designation receipts. It does not reproduce vendor exchange clusters or assume this partial sample equals vendor totals. See `data/reference/vendor_claims.csv` and `docs/PRIOR_ART.md` for the claims and scope limits.
