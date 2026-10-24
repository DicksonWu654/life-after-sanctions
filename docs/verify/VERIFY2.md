# Independent verification 2 — saved-data audit

Run on 2026-10-23 with `.venv/bin/python -S scripts/verify/verify2.py --live`. This script reads `data/addresses.csv`, `data/ledger.csv`, saved timelines, and saved price CSVs. It does **not** import `scripts/analysis/*` or their derived address summaries. `data/verify/verify2_manifest.csv` records the compressed-byte SHA-256 and path for each of the 1,043 timelines read. Live responses are gzip-compressed under `data/raw/verify2/`; each row of `data/verify/verify2_live.csv` gives the exact request URL and response path. Results remain a provisional saved-data snapshot while source fetchers run. Research, not legal or compliance advice.

| Claim | Verdict | Independent result | Evidence |
| --- | --- | --- | --- |
| A. Already empty when listed | **CONFIRMED** | 497 chain-address pairs; 48 had the last qualifying outflow in the 30 days before T, 449 earlier. | `data/verify/verify2_empty.csv`; `data/verify/verify2_addresses.csv` |
| B. Seven-day net depletion | **CONFIRMED** | 6.4044059827% of eligible designation-date USD value, held at each address's own T prices. It rounds to **6.40%** at two decimals. | `data/verify/verify2_depletion.csv` |
| C. Pre-listing week | **CONFIRMED** | 49/887 = 5.5242% active in the last week, against 15.3497% mean own-baseline weekly activity. The one-sided rank test gives p = 1.0000 for excess. | `data/verify/verify2_premove.csv` |

The current `FINDINGS.md` says 497, 6.40%, and 49/887 (5.52%) with a 15.35% baseline. Earlier text quoted 6.41% and 42/833 or 48/885; those are superseded by the saved result snapshot. The exact B numerator and denominator independently equal `results/checkpoints.json`; C equals `results/premove.json`. No statistical statement here establishes anticipation, intent, control, or unlawful conduct.

## Shared clock and population

T is 00:00 **America/New_York** at `first_listed_date`, not midnight UTC or the unknown publication hour. T balance includes confirmed flows strictly before T; T+7 uses the same Eastern calendar clock seven days later. The three, seven, and fourteen-day pre-windows are half-open `[T-w,T)`, so designation-day activity is excluded. Eastern daylight-saving shifts are handled as calendar dates. `data/addresses.csv` supplies one chain-address pair per row; ledger entity UIDs are attached but never used as an address multiplier. Same-string activity on a different EVM chain is outside these counts. All 91 Tornado-associated identifiers are excluded from these wallet headlines under the shared definition. The trackable, non-Tornado population with a readable timeline is 1,043 pairs; 1,031 have `coverage.complete=true`, and 1,009 have a fully reconciled recognised-asset T checkpoint under this audit. The 14 untrackable ledger pairs remain outside the 1,043 trackable denominator; they are not silently classified as zero.

The audit replays confirmed signed asset amounts from zero, including sender fees on failed EVM transactions. It checks each reconstructed asset against the saved observed latest balance, and checks negative paths at timestamp-group boundaries. A positive balance below USD 1 is **not** zero. The only zero tolerance is `1e-15` asset units for decimal arithmetic residues. An unreconciled recognised asset makes a full-address checkpoint unknown. An unrecognised token is outside measured recognised assets, even if the explorer reports its symbol as a familiar one. Exact contract IDs, not ticker strings, control token recognition. Price lookup uses saved hourly close observations when at most two hours old, otherwise saved daily observations when at most two days old; missing price is unknown, never zero. Price rows carry original `source_url` and `raw_ref` to the compressed API response. The audit's per-address tables carry timeline paths and the listing action URL, and timeline rows carry transaction `raw_ref` values.

## A — zero recognised-asset balance at T after earlier outflow

The numerator requires a complete and reconciled recognised-asset history, zero of every recognised asset at T, and at least one earlier confirmed non-self outward transfer worth at least USD 1 at its transfer time. The last such outflow defines the 30-day split. It is a timing description, not proof that a particular transfer caused the final zero if later receipts and outflows occurred. Coverage means **no measured balance in recognised assets on the listed chain**; it does not mean no other tokens, other-chain holdings, or off-address assets.

| Chain | Empty with prior outflow | Last outflow ≤30d before T | Last outflow >30d before T | Evidence |
| --- | ---: | ---: | ---: | --- |
| BTC | 450 | 46 | 404 | `data/verify/verify2_empty.csv#chain=BTC` |
| ETH | 19 | 0 | 19 | `data/verify/verify2_empty.csv#chain=ETH` |
| LTC | 13 | 1 | 12 | `data/verify/verify2_empty.csv#chain=LTC` |
| TRX | 5 | 1 | 4 | `data/verify/verify2_empty.csv#chain=TRX` |
| BCH | 4 | 0 | 4 | `data/verify/verify2_empty.csv#chain=BCH` |
| DASH | 4 | 0 | 4 | `data/verify/verify2_empty.csv#chain=DASH` |
| BSV | 1 | 0 | 1 | `data/verify/verify2_empty.csv#chain=BSV` |
| DOGE | 1 | 0 | 1 | `data/verify/verify2_empty.csv#chain=DOGE` |
| **Total** | **497** | **48** | **449** | `data/verify/verify2_empty.csv` |

497/1,043 = 47.65% of trackable non-Tornado pairs with timelines; 497/1,009 = 49.26% of pairs with a fully reconciled recognised-asset T checkpoint. The spot check below uses 20 different BTC addresses and 20 distinct transactions, ten from each timing group. For each, the live mempool.space `/api/address/{address}/txs` response contains the complete 2–14 transaction history, identifies the saved last pre-T debit as the latest pre-T debit, and replays to **0.00000000 BTC** at T. These checks validate those BTC examples and their local timeline extraction; they do not directly validate the non-BTC rows. The address and transaction links are live explorer URLs; the cached API request URL and response path are in `data/verify/verify2_live.csv`.

| Timing | Address explorer | Last pre-T outgoing transaction | Last out UTC | Live T BTC |
| --- | --- | --- | --- | ---: |
| ≤30d | [35irs2AU6pVgenYbWvMRz22avDBLC9XMkd](https://mempool.space/address/35irs2AU6pVgenYbWvMRz22avDBLC9XMkd) | [b9b8a496ae219a…](https://mempool.space/tx/b9b8a496ae219ae3da77d9b6f90527cd0a49d90b34938c63a410951721d3c242) | 2025-10-15 | 0.00000000 |
| ≤30d | [bc1q6qze6uj6jncgnva4eghxn3tr4pm2frh77ad3k9](https://mempool.space/address/bc1q6qze6uj6jncgnva4eghxn3tr4pm2frh77ad3k9) | [2f07391e3c91c7…](https://mempool.space/tx/2f07391e3c91c70ccdd8b21d90216dc56e654668e40493f0090053dfe279a956) | 2025-10-15 | 0.00000000 |
| ≤30d | [bc1q86tl9255vg5wldamfymaaz36uqxzm30gs7fhkljvzdlt9t38s3lqgdwdfq](https://mempool.space/address/bc1q86tl9255vg5wldamfymaaz36uqxzm30gs7fhkljvzdlt9t38s3lqgdwdfq) | [696c8e1df4b3e1…](https://mempool.space/tx/696c8e1df4b3e1c4ddb47bac2bd862f1a600092b1c050aacc2723e020db449ef) | 2021-10-27 | 0.00000000 |
| ≤30d | [bc1qe95l438kzjcvnsm3kn8n5augf9gpctdlhsq7f7hpnkyvlr7rc7cqupapf7](https://mempool.space/address/bc1qe95l438kzjcvnsm3kn8n5augf9gpctdlhsq7f7hpnkyvlr7rc7cqupapf7) | [f3df673588856f…](https://mempool.space/tx/f3df673588856f1e84f47a560634b04d640d6f6fcc6bc37d241b2b939bee6a6a) | 2021-10-25 | 0.00000000 |
| ≤30d | [bc1qu4p4eynzu8vwwcv0yxq74gth00exjyech05uf0](https://mempool.space/address/bc1qu4p4eynzu8vwwcv0yxq74gth00exjyech05uf0) | [63605491f429f9…](https://mempool.space/tx/63605491f429f9ef6e83f52d0fd56416cc1745a2d41ff89cecae0623a92f7dd1) | 2025-10-15 | 0.00000000 |
| ≤30d | [bc1qw7vfgv3r5vnehafl0y95sclg3uqsj87wxs9ad628yjjcq33cwessr6ndyw](https://mempool.space/address/bc1qw7vfgv3r5vnehafl0y95sclg3uqsj87wxs9ad628yjjcq33cwessr6ndyw) | [adfc3a9169e945…](https://mempool.space/tx/adfc3a9169e9458286a79b30f4a9c5432a848e3349475d1bdd2bf323991fd438) | 2021-10-26 | 0.00000000 |
| ≤30d | [bc1q2lpgjntr348pfvxhfy33ehmdzy3gmx8w4052z6](https://mempool.space/address/bc1q2lpgjntr348pfvxhfy33ehmdzy3gmx8w4052z6) | [ab23fb5013fb7a…](https://mempool.space/tx/ab23fb5013fb7ad9d18d8d8dd4da71627ed2242f4a8dede5123a6a1e5abe695e) | 2022-09-14 | 0.00000000 |
| ≤30d | [bc1q90zrdysy4flyacw7hsury3ajs9yzwtwp6guqpypx94w0d3p58hysvz6pde](https://mempool.space/address/bc1q90zrdysy4flyacw7hsury3ajs9yzwtwp6guqpypx94w0d3p58hysvz6pde) | [9335dc415fb135…](https://mempool.space/tx/9335dc415fb13500ca9263e0b06dcca82b1b90c5fc8ae4fe380c8fe9c7a2504c) | 2021-10-26 | 0.00000000 |
| ≤30d | [1CPJak9ZyddbawMGJPyEhCiJLXXb4sYv8N](https://mempool.space/address/1CPJak9ZyddbawMGJPyEhCiJLXXb4sYv8N) | [955a4451d6c555…](https://mempool.space/tx/955a4451d6c55557721bceb4a6763e215d4bb1fb4d9246f09ca1a8885c8dac42) | 2023-04-15 | 0.00000000 |
| ≤30d | [15yqWQ4sqr7jzCwDtZ3U1KaCa8WMEy7Mm2](https://mempool.space/address/15yqWQ4sqr7jzCwDtZ3U1KaCa8WMEy7Mm2) | [c0dacb7072d5c2…](https://mempool.space/tx/c0dacb7072d5c286de1fc2af5ba216f57e09bf35b55489e536a0cb8ef7db3173) | 2022-11-08 | 0.00000000 |
| >30d | [123WBUDmSJv4GctdVEz6Qq6z8nXSKrJ4KX](https://mempool.space/address/123WBUDmSJv4GctdVEz6Qq6z8nXSKrJ4KX) | [d116b2dcbafc3c…](https://mempool.space/tx/d116b2dcbafc3c10cc4f55014108e79797d7da45eebcbc5e60764bd768100b7f) | 2020-02-18 | 0.00000000 |
| >30d | [125W5ek3DT6Zqy5S2iPt4FHQdNMCbZA3FU](https://mempool.space/address/125W5ek3DT6Zqy5S2iPt4FHQdNMCbZA3FU) | [b2f81aef851d6b…](https://mempool.space/tx/b2f81aef851d6bbb2888b70ce625524b4810a47cc5e7c2056058fe61de3fd5a7) | 2021-06-29 | 0.00000000 |
| >30d | [12YCfVAEzkEZXBYhUTyJJaRkgMXiFxJgcu](https://mempool.space/address/12YCfVAEzkEZXBYhUTyJJaRkgMXiFxJgcu) | [c6ebb8eb5fa713…](https://mempool.space/tx/c6ebb8eb5fa7130279a9dd21ad6198cb39fd837cb37824b255dac095d89c5761) | 2021-05-10 | 0.00000000 |
| >30d | [12YyR9EpvHxBjjKjTWqfKqeyoWnvcraxpW](https://mempool.space/address/12YyR9EpvHxBjjKjTWqfKqeyoWnvcraxpW) | [d1f705c11e28c6…](https://mempool.space/tx/d1f705c11e28c6c1fca76f0033fa04523400d41632c2c10e707f83fe4aa30363) | 2018-10-15 | 0.00000000 |
| >30d | [12jVCWW1ZhTLA5yVnroEJswqKwsfiZKsax](https://mempool.space/address/12jVCWW1ZhTLA5yVnroEJswqKwsfiZKsax) | [22e52921af2a5b…](https://mempool.space/tx/22e52921af2a5bd8b65edbd9e0ea2c7f0745b9583528ecb6e27be9576e4fc805) | 2021-05-14 | 0.00000000 |
| >30d | [12mNKr2YP4M3CEQvCvVqZsvxuCG47LHMu1](https://mempool.space/address/12mNKr2YP4M3CEQvCvVqZsvxuCG47LHMu1) | [5841ef0f1e5712…](https://mempool.space/tx/5841ef0f1e57120763f6a04e369225b0d9da4c307d135e577508c347696f5eb8) | 2020-04-17 | 0.00000000 |
| >30d | [12w6v1qAaBc4W8h8C2Cu5SKFaKDSv3erUW](https://mempool.space/address/12w6v1qAaBc4W8h8C2Cu5SKFaKDSv3erUW) | [bc4b07549660af…](https://mempool.space/tx/bc4b07549660afd05dc007b244156283992370920823193f753289a460ff9416) | 2021-07-06 | 0.00000000 |
| >30d | [13JtX4h7G5ZuNK5mFudKGq9DHLvvMFuNuz](https://mempool.space/address/13JtX4h7G5ZuNK5mFudKGq9DHLvvMFuNuz) | [e3adf78dc1ce25…](https://mempool.space/tx/e3adf78dc1ce252c16dede3760d5e13d43222fc1b851096da997b48eb5fb43cb) | 2018-11-15 | 0.00000000 |
| >30d | [13YBQr2Cp1YY3xqq2qngaPb7ca1o4ugeq6](https://mempool.space/address/13YBQr2Cp1YY3xqq2qngaPb7ca1o4ugeq6) | [90348444f253f9…](https://mempool.space/tx/90348444f253f996d96ece234d251c0fde3fc600318d50acaf4ee94d9afbf817) | 2017-05-30 | 0.00000000 |
| >30d | [14gM1HuLVDELNHaFU22qpabjtiWek4HhV1](https://mempool.space/address/14gM1HuLVDELNHaFU22qpabjtiWek4HhV1) | [2da7e82b2fd72c…](https://mempool.space/tx/2da7e82b2fd72cb4d0c6f319a8d0c4f7a190be4d8497188c98d7842f4f14afab) | 2020-11-11 | 0.00000000 |

## B — value depletion within seven Eastern calendar days

For each recognised, reconciled, priced asset with positive T balance, the audit computes `max(0, balance_T - balance_T+7) × price_T`. It sums that **net** depletion and divides by the same assets' `balance_T × price_T`. Prices are held at each address's own T, so price movements do not produce the depletion figure. Receipts can offset withdrawals; this is not gross outward volume, lot tracing, spendability, or a claim about the same pool of dollars across different designation dates. Only pairs with complete histories, full recognised-asset reconciliation, positive priced value at T, and a covered T+7 checkpoint enter the cohort.

| Cohort | Pairs | T-value denominator, USD at each own T | Net depleted, USD at T prices | Share | Evidence |
| --- | ---: | ---: | ---: | ---: | --- |
| All eligible non-Tornado | 491 | 4,124,244,055.86 | 264,133,333.05 | 6.4044% | `data/verify/verify2_depletion.csv` |
| Excluding all 10 pairs listed under SDN UID 55505 (CHEN, Zhi) | 481 | 1,510,159,180.57 | 264,133,333.05 | 17.4904% | `data/verify/verify2_depletion.csv#sdn_uids!=55505` |
| Excluding exchange-scale pairs (>10,000 distinct observed transaction hashes) | 471 | 4,106,333,353.78 | 264,131,700.43 | 6.4323% | `data/verify/verify2_depletion.csv#exchange_scale=False` |

The largest named entity's ten pairs account for USD 2,614,084,875.29 of this mixed-T value denominator and no measured seven-day net depletion, which explains the larger exclusion share. The exchange-scale rule uses observed distinct hashes; a partial history may conceal scale, so this exclusion is a sensitivity, not a definitive exchange classification. Address/entity membership overlaps elsewhere; no entity-level value is added to the address total. `data/verify/verify2_depletion.csv` gives each address's T time, T USD, depleted USD, scale flag, action URL and timeline reference. The price CSVs under `data/prices/` point to the raw API response and request URL for each selected T observation.

## C — own-week pre-listing outflow

An eligible address has a complete saved history, a first confirmed transaction before the event window, and at least 12 comparable earlier windows. Baseline windows end at T−35, T−42, T−49, … Eastern calendar days and end before the final 30-day buffer. Transfers are confirmed, outward, non-self, recognised-asset, and at least USD 1 at transfer time. Baseline share is first calculated per address, then averaged equally across eligible addresses. This is an address share, not an entity share.

| Window | Population | Eligible pairs | Event active | Event share | Mean own-baseline active share | Mean address midrank | One-sided cluster p for excess | Evidence |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 3d | All eligible | 888 | 42 | 4.73% | 11.36% | 0.4674 | 1.0000 | `data/verify/verify2_premove.csv#window_days=3` |
| 7d | All eligible | 887 | 49 | 5.52% | 15.35% | 0.4516 | 1.0000 | `data/verify/verify2_premove.csv#window_days=7` |
| 14d | All eligible | 879 | 67 | 7.62% | 18.82% | 0.4449 | 1.0000 | `data/verify/verify2_premove.csv#window_days=14` |
| 3d | Active in prior 180d | 245 | 42 | 17.14% | 28.43% | 0.4449 | 0.9968 | `data/verify/verify2_premove.csv#window_days=3;dormant_prior_180d=False` |
| 7d | Active in prior 180d | 244 | 49 | 20.08% | 38.11% | 0.4117 | 1.0000 | `data/verify/verify2_premove.csv#window_days=7;dormant_prior_180d=False` |
| 14d | Active in prior 180d | 239 | 67 | 28.03% | 46.28% | 0.4110 | 1.0000 | `data/verify/verify2_premove.csv#window_days=14;dormant_prior_180d=False` |

The midrank includes the actual window among each address's baseline windows with ties preserved. Its null center is 0.5. The primary seven-day connected-component score is **−0.0918624** over **59 components** linked by shared first-publication action or SDN UID. A one-sided 9,999-draw conditional Bernoulli rank randomization with seed 20261023 gives **p = 1.0000** for an excess; shorter/longer and active-only checks likewise show no excess. This is a diagnostic under exchangeability of an address's weeks and the stated component dependence model, not a causal test. Unequal history lengths, trends, common shocks, seizures, and source gaps can change the baseline comparison. The result supports **“no cohort-wide excess observed within this data and test”**, not proof that no individual moved before notice.

## Coverage and definitional limits

- **Unknown publication hour:** T is a date boundary. A transfer during listing day is omitted from C and belongs to the post-T checkpoint interval even if it preceded publication that day. Actual intraday notice cannot be inferred.
- **Multiple OFAC entities:** one chain-address pair is counted once at its earliest listing date. A pair can carry several SDN UIDs; the largest-entity sensitivity removes any pair carrying UID 55505. Named entities are OFAC labels, not a claim about a controller.
- **Recognised assets and prices:** unknown contracts and unpriced recognised tokens cannot be asserted absent. Full-address checkpoints require reconciliation of all recognised assets. B's USD total uses only recognised assets with saved T prices and mixes historical T dates. Small positive balances are not zero.
- **Same address elsewhere:** another EVM chain under the same `0x` string is a separate chain-address pair. This audit measures activity on the listed chain only.
- **Coverage:** 12 of 1,043 trackable non-Tornado timeline histories are marked incomplete; a further 22 fail this audit's full recognised-asset reconciliation. They are excluded from measured zero claims, not treated as non-movers. The live explorer spot check covers BTC examples only; other chains rest on their saved raw responses. “No outflow found” always means within checked assets, dates, and source history.

Reproduction: `.venv/bin/python -S scripts/verify/verify2.py` recomputes the offline tables; add `--live` for the 20 cached explorer checks. The CSVs preserve the address-level independent evidence.
