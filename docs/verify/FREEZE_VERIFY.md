# Independent issuer-freeze verification

Run: `.venv/bin/python scripts/verify/freeze_verify.py --check` (offline). Raw HTTP responses: `data/raw/verify_freeze/`. Evidence rows: `data/verify/freeze_verify.csv` (558 rows).

## Scope and results

Tron snapshot began at block **87,361,367** (2026-10-23T12:07:42Z), raw `data/raw/verify_freeze/tron_block/2b9e7235c977689b0164a91c5cce75103630d6ca91bf81ca4d2cdd6db661e671.json.gz`. Contract calls made for every address over a moving latest-block window, so the two current-state calls per address are not atomic. Ethereum's initial block-height reference was **26,255,229**, raw `data/raw/verify_freeze/eth_block/03d4a21805b28c6b5ae7364e1e41e16996f9a3c1bc6e4e07d7fd34c88fce6e45.json.gz`; the 20 eth_call requests used `latest` over a moving window because the public RPC restricts historical calls. T_pub is 12:00 America/New_York on the first address listing date.

| Claim | Verdict | Independent result |
|---|---|---|
| (a) Tether ever blacklisted all 341 OFAC Tron addresses | CONFIRMED | 341/341 have a first AddedBlackList event in the complete contract event crawl; 341/341 currently return true from getBlackListStatus. Current balanceOf is positive for 217/341 addresses. |
| (b) Median signed lag about −7.3 h; 96 definitely before listing day | CONFIRMED | Median -7.312 hours; 96 events precede 00:00 ET on the first listing date. |
| (c) About 529M USDT held by all 341 at first freeze | ADJUSTED | Corrected wording: 529,064,435.426376 USDT is the rederived **known-balance subtotal for 334/341 addresses**; 7 first-freeze balances remain unknown, so there is no verified all-address total. Daily-price proxy valuation of the known subtotal: 529,081,410.568 USD across different freeze dates. |
| (d) Circle ever blacklisted 216/217 ETH identifiers; median 8.3 h | CONFIRMED | 216/217 have a Blacklisted event in the independent Blockscout contract-log crawl; median signed lag 8.310 hours. Public RPC eth_call at `latest` checked 20 valid 0x identifiers (20 agree with the proposed current state). The 217th ledger string has 39 hex digits and is invalid for ABI address calls. |

## Denominators and method

`data/ledger.csv` independently contains 341 distinct TRX addresses; `data/addresses.csv` contains 341. Set differences: 0; first-date differences: 0. ETH inventory has 217 distinct strings. No prior freeze code was imported. The original candidate ranking, prepublication stratum, and 334-address known-balance cohort were frozen in `data/raw/verify_freeze/claim_baseline.json.gz` to preserve the baseline despite a concurrent refresh of the derived CSV. That later refresh newly measured `TYq3iRujcBELXX89i9JY32UmLxcyZAJe7E`; this report tests the original 529,064,435.426376 USDT claim. No proposed event timestamp or amount was accepted as evidence.

The Tron contract event crawl saved 46 pages and reached its terminal page. First event is the earliest AddedBlackList by block time for each address. Circle Blacklisted logs came from 1 Blockscout page(s), terminal page reached, and were matched by the indexed address topic. The stratified sample has 40 unique Tron addresses: top 10 proposed balances, 10 other proposed definitely-prepublication cases, and 20 spread over OFAC action dates. Separate transaction event queries confirmed 40/40 first events. OFAC Recent Actions HTML printed the listed identifier in 40/40 pages; the URL date was separately checked in the CSV.

The verifier reparsed existing saved TronGrid HTTP responses listed in `data/raw/verify_freeze/archive_manifest.json.gz` to reconstruct balances; these source captures were collected by the source pipeline and were **not** treated as derived balances. It independently closed pagination and time-range coverage for 297/334 claimed-known histories; fresh TronGrid histories closed for 96 addresses and matched the archived result exactly for 96. Combined coverage checks close 304/334 claimed-known histories, including 40/40 of the stratified sample and 11/15 of the top 15. Remaining archived balances reproduce the source captures but their page continuity is not independently proven. 7 addresses in the original claim cohort lack a defensible first-freeze amount; partial sums appear in the CSV only as diagnostics and are excluded from totals.

TronGrid transfer rows lack block/log indices, so 0 address histories with a transfer at the freeze timestamp have same-block order ambiguity. USD valuations apply Coin Metrics USDT PriceUSD with a daily series timestamp on each freeze's UTC date (raw `data/raw/verify_freeze/prices/54f9c7d40bc63c971555aed53180a6e4d53fbf064b732ab13c381650a29e4910.json.gz`), not a quote at the freeze second. The current balance is a later snapshot and is not substituted for historical balance.

Offline reproduction requires both `data/raw/verify_freeze/` and the referenced `data/raw/tron/trc20/` captures. The public repository excludes these saved responses; the request index preserves their acquisition identities.

## Top 15 claimed contributors, independently reconstructed

| Address | OFAC name | First-freeze USDT | Action | Event transaction |
|---|---|---:|---|---|
| `TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 212,922,653.485554 | [2026-04-24](https://ofac.treasury.gov/recent-actions/20260424) | [ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe](https://tronscan.org/#/transaction/ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe) |
| `TTiDLWE6fZK8okMJv6ijg42yrH6W2pjSr9` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 131,288,800.972952 | [2026-04-24](https://ofac.treasury.gov/recent-actions/20260424) | [295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a](https://tronscan.org/#/transaction/295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a) |
| `TFQbqaNbmq2xsVor2NbufLkYZvxFC9wC7k` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 85,527,016.000000 | [2026-07-14](https://ofac.treasury.gov/recent-actions/20260714) | [005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4](https://tronscan.org/#/transaction/005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4) |
| `TJdgB1k6ot3f2nLuZug6D8eD3HavTmzmSK` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 30,978,224.260461 | [2026-07-14](https://ofac.treasury.gov/recent-actions/20260714) | [8711a45933c3ca6b4c14c346362c24daa3a115060d5e7f3aa4e17312dc2b5ade](https://tronscan.org/#/transaction/8711a45933c3ca6b4c14c346362c24daa3a115060d5e7f3aa4e17312dc2b5ade) |
| `TXGHxdYbGy574z5hBu4LNzq9NzjZQ9bhUf` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 12,306,816.477870 | [2026-07-14](https://ofac.treasury.gov/recent-actions/20260714) | [e03618db94e6410790b4ede0eba847d54c1d50cce635a1d54d574ef0ed2ec923](https://tronscan.org/#/transaction/e03618db94e6410790b4ede0eba847d54c1d50cce635a1d54d574ef0ed2ec923) |
| `TWPma8xH48AEN93x2krdukV9e1j6sPsBeS` | XINBI GUARANTEE | 9,705,239.643337 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [4a32673d3978ead1895d3d1401b87656b36ade974458785bc201384e1468dbb7](https://tronscan.org/#/transaction/4a32673d3978ead1895d3d1401b87656b36ade974458785bc201384e1468dbb7) |
| `TQhT3QWAbFiy6GEYuBrbK97uP3XVmTpRD8` | XINBI GUARANTEE | 8,000,026.000013 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [9f16893c8ae68ca310f867d3e3dde7067be549629ca9f7772d1c73ea1b0056ae](https://tronscan.org/#/transaction/9f16893c8ae68ca310f867d3e3dde7067be549629ca9f7772d1c73ea1b0056ae) |
| `THH9JJNbLDN7qs1CyTxJQEjhC9y5FnZUhU` | XINBI GUARANTEE | 8,000,024.400013 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [88976e94f1aa1f7be5fc7148eb607629ac44f64b7fd92ba419cf8bb2ef948d53](https://tronscan.org/#/transaction/88976e94f1aa1f7be5fc7148eb607629ac44f64b7fd92ba419cf8bb2ef948d53) |
| `TXka5xc6mEkcoVXR7F2TFDKernyLt3XyW4` | XINBI GUARANTEE | 8,000,002.000001 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [e1007b4d83fd77d31b212e06ade5057b8af3df521c38934e681b5ab6d17a7f3d](https://tronscan.org/#/transaction/e1007b4d83fd77d31b212e06ade5057b8af3df521c38934e681b5ab6d17a7f3d) |
| `TCA9vmjsYw9MtPKEwRBtGhKFRfr4CLxJAv` | ZEDCEX EXCHANGE LTD | 2,000,012.000002 | [2026-01-30](https://ofac.treasury.gov/recent-actions/20260130) | [d091798ef277a226866d7d17209dc99a305ff1effb80b52492d65c71e854ebfc](https://tronscan.org/#/transaction/d091798ef277a226866d7d17209dc99a305ff1effb80b52492d65c71e854ebfc) |
| `TG83Fk56S2mycAUMYHZyZp9wMg6DCf4bUn` | XINBI GUARANTEE | 1,986,132.286771 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [390ea07181a989f189a1269e954663c18823a20f02f5dde93655b9f7dc7bc88d](https://tronscan.org/#/transaction/390ea07181a989f189a1269e954663c18823a20f02f5dde93655b9f7dc7bc88d) |
| `TLHWeZcDmXk6idnaGwsQ9CEmK24KpoGgRM` | XINBI GUARANTEE | 1,891,066.615000 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [6db22188d2d3231a8fc749fa82ede67cfceb18d4a95def16260eef1945cbfa2b](https://tronscan.org/#/transaction/6db22188d2d3231a8fc749fa82ede67cfceb18d4a95def16260eef1945cbfa2b) |
| `TAhwhFv3JpK39Nc2m8W5LPCcoTisutiRfp` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 1,285,180.481394 | [2026-07-14](https://ofac.treasury.gov/recent-actions/20260714) | [01f768c5d6e8ad54d93bb930064a70ba386f175854d52ab1b8effd07060cdf39](https://tronscan.org/#/transaction/01f768c5d6e8ad54d93bb930064a70ba386f175854d52ab1b8effd07060cdf39) |
| `TF7LUSoZQyDFxTFzCL11saBHAqMAyPh8dK` | XINBI GUARANTEE | 1,261,033.469089 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [b130541b426b7c18fed2ae611e4809a2cebc184acf685cda11085bb919552f06](https://tronscan.org/#/transaction/b130541b426b7c18fed2ae611e4809a2cebc184acf685cda11085bb919552f06) |
| `TR983hNyUNgrNSB1xncG9thZNhgYpbNvSh` | XINBI GUARANTEE | 1,201,069.572924 | [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | [24c4ab5eb32c511198ffefd52488a49573bcff058ccb68581846a4ed92b1be4b](https://tronscan.org/#/transaction/24c4ab5eb32c511198ffefd52488a49573bcff058ccb68581846a4ed92b1be4b) |

### OFAC actions represented among the top 15

| Action date and source | Addresses | OFAC names | First-freeze USDT |
|---|---:|---|---:|
| [2026-01-30](https://ofac.treasury.gov/recent-actions/20260130) | 1 | ZEDCEX EXCHANGE LTD | 2,000,012.000002 |
| [2026-04-24](https://ofac.treasury.gov/recent-actions/20260424) | 2 | BANK MARKAZI JOMHOURI ISLAMI IRAN | 344,211,454.458506 |
| [2026-07-14](https://ofac.treasury.gov/recent-actions/20260714) | 4 | BANK MARKAZI JOMHOURI ISLAMI IRAN | 130,097,237.219725 |
| [2026-09-09](https://ofac.treasury.gov/recent-actions/20260909) | 8 | XINBI GUARANTEE | 40,044,593.987148 |

**Top-15 sum:** 516,353,297.665381 USDT at each address's first freeze, 97.60% of the known subtotal; proposed top-15 sum 516,353,297.665381 USDT; difference 0.000000 USDT. The independently reprocessed 334-address known subtotal is 529,064,435.426376 USDT (529,081,410.568 USD under daily UTC price labels). The proposed known subtotal is 529,064,435.426376 USDT, a difference of 0.000000 USDT. The proposed USD subtotal is 529,155,483.918; the daily-price convention here gives -74,073.350 USD difference. Check each row's transfer, price, and event raw refs in the CSV.

**Unknown first-freeze balances in the frozen original capture:** `TNUQ2rZSRjZaGhtbwaFZEvuaemMj5z5Fnm`, `TNwe3WoEX6XrQ5NPAeWPkvpTtdaf27XYxK`, `TSmcHwvTR27Ao4NN8HhPFCVcPU5aTEqLDt`, `TW5tokvhEfrb77z98Rc8HqbkzQJ6sxYtGX`, `TWqcMjV7Wq2RHe2CSiKQHpkn6A7B2AWUPe`, `TXHX2NUvcgft4zs6MkkUtdNVERPTavHDWN`, `TYq3iRujcBELXX89i9JY32UmLxcyZAJe7E`. Their diagnostic partial sums are excluded. A later parallel refresh completed one of these histories, as noted above.

**OFAC action-page exceptions in the 40-address sample:** 0. Every sampled page contained the exact address and its URL date matched the ledger's first listing date.

## Methodological concerns

- An OFAC Recent Actions date is a calendar date. The noon ET publication proxy is an analysis convention, not an observed publication timestamp. Only events before 00:00 ET prove pre-day ordering; they do not show why an issuer acted earlier.
- OFAC pages are checked for the exact address string and action-date URL in the sample. A later addition to an already-designated entity must use that address-addition action, not the entity's original designation date. The CSV keeps the action URL per row.
- 42 of the 96 pre-day Tron events are more than 30 days before the first OFAC address-listing date. For example, `TScXZTbDjjZ6a6jiC7dZjgCqfNo4vm7atV` was frozen long before its listed action (event and action refs in the CSV). Tether may have acted for an unrelated reason; temporal ordering does not establish advance knowledge, coordination, or a legal conclusion.
- 'Ever blacklisted' is an event-history measure; `getBlackListStatus` is current state. An eventual unblacklisting would not erase the historical event. Circle's 20 `latest` eth_call results assess current state over a moving window; the independent Blockscout event crawl establishes the historical count and median.
- USDT totals are native token units. The USD estimate sums daily-price valuations across different freeze dates, not cash held at one time; the Coin Metrics series labels each price at 00:00 UTC rather than the exact freeze second.

This is research, not legal or compliance advice.
