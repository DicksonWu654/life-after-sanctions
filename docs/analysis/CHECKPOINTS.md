# Checkpoints — completed bounded snapshot

Saved-data read pass completed 2026-10-23T21:08:25.221806+00:00. **Provisional: false. Bounded acquisition finished; per-chain, asset and reconciliation gaps remain.**

Research, not legal or compliance advice. No outflow found means within the data checked. Identifiers and SDN UIDs are not persons or proof of control.

## Coverage and outputs

| Measure | Count | Unit |
|---|---:|---|
| ledger_addresses | 1148 | addresses |
| ledger_addresses_with_readable_timelines | 1147 | addresses |
| ledger_addresses_without_readable_timelines | 1 | addresses |
| unreadable_or_partial_files | 0 | files |
| nonledger_timelines | 1086 | chain-address timelines |
| complete_ledger_histories | 1095 | addresses |
| ledger_addresses_with_T_balance | 1058 | addresses |
| ledger_addresses_with_today_balance | 1116 | addresses |

`data/derived/address_summary.csv` has one row per listed chain-address plus explicitly separated same-address other-EVM-chain rows. Its `checkpoints` JSON cell holds per-asset native quantities, historical USD, requested/actual valuation times, price observations and raw references; `reconciliation` exposes pass/fail per asset. Booleans are True/False; an empty scalar cell or JSON null means unknown, never zero. USD scalar column units are in their names. `share_T_balance_gone` is a fraction (0–1), and lag columns are days. `examples` contains transaction hashes, explorer URLs, timeline row indexes and saved API/price evidence.

`results/checkpoints.json` contains compact address indexes, all aggregates, rankings, candidate findings, source hashes and the timeline manifest. Source request metadata is in the gzip referenced by each timeline row (or the adjacent price `.request.json`). T comes from `data/addresses.csv`; match the chain/address in `data/ledger.csv` for `listed_raw_ref`, `listed_action_url` and `listing_events` providing its OFAC publication evidence. Aggregate rows point to the address CSV and explicitly name their filters; program and entity memberships overlap.

### CSV detail encoding

Long evidence strings are losslessly deduplicated inside each row. `unpack_detail(checkpoints, reconciliation, examples)` in the script restores conventional per-checkpoint objects. For `columnar-v1`, checkpoint `labels` fixes the order; `times`, `usd`, `priced_subtotal_usd`, `missing`, and `unrecognised_positive` follow that order. Each `assets[asset]` is `[symbol, native, usd, valued_at_ref, price_id, method, raw_ref_id]`. A scalar series repeats at every checkpoint; a list has one item per label. Methods: 0 unavailable, 1 reconciled transfer history, 2 observed state. Reference IDs index `refs` (which may hold a string or a raw-reference list). Each `prices[id]` is `[price_usd, observed_time_ref, source_ref, raw_ref_id, source_url_ref]`. Each reconciliation `assets[asset]` is `[symbol, reconstructed_native, observed_native, minimum_native, pass, historical_usable, same_history_block, raw_ref_id]`. Examples share those refs/prices and store unique events once; named example fields are event indexes or lists of indexes. Native quantities are decimal strings in the asset’s own units; USD series are checkpoint-time USD, prices are USD per unit, and missing/unknown series count assets. The compact format avoids a large repeated-evidence file while preserving quantities and their provenance.

## Reproduce

```sh
.venv/bin/python -S scripts/analysis/checkpoints.py
.venv/bin/python -S scripts/analysis/checkpoints.py --self-test
.venv/bin/python -S scripts/analysis/checkpoints.py --check
```

`--check` recomputes the saved timeline-file manifest offline and compares the saved result and CSV. Newly arrived files are outside that published snapshot; changed existing files correctly produce a diff. Rerun the default command to refresh. Inputs are not locked: each timeline is read once, hashed, and unreadable/partial files are skipped and counted. JSON/gzip parse errors do not stop other addresses. A parseable incomplete history stays flagged. This check runs offline without credentials.

## Candidate findings

### value_denominator_concentration

**63.3834% share** — Share of the observed seven-day T-value denominator attached to SDN UID 55505 (CHEN, Zhi).

Confidence: Describes address-list concentration, not beneficial ownership, spendability or custody. Public seizures and freezes can leave funds at listed addresses. Entity footprints overlap; do not add them. See exclusion sensitivity.

- BTC [f48cf5b99ddc02047e57fec74391e608d9c66110a532b05533560cd460ca4c16](https://mempool.space/tx/f48cf5b99ddc02047e57fec74391e608d9c66110a532b05533560cd460ca4c16) — 2023-03-05T20:01:48Z; 2999.00000000 native:BTC; 67194666.02 USD at transfer time. Address `bc1q2we5eqjj8je6lz9xwjattpc3pn4jejc5h0s70f` (CHEN, Zhi), first listed 2025-10-14. Raw: `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[3]`; price raw: `data/raw/prices/binance/BTC-1H/b72c2c8135143abc07a745371b586ee33488ac4ba367fd634239af382f38fcba.json.gz#row=235;data/raw/prices/binance/USDT-HOURLY-FX-1H/b604cf2ef8dd92cdeb9961296c057df3090851abea8ee63e738be0236138ca28.json.gz#row=85`.
- BTC [e4ff7e122afdf1fc50ffa05030cd8615522ac887e8f83e37cf7ad5bbf5f13ac4](https://mempool.space/tx/e4ff7e122afdf1fc50ffa05030cd8615522ac887e8f83e37cf7ad5bbf5f13ac4) — 2025-10-15T06:10:22Z; 400.00000000 native:BTC; 44999779.87 USD at transfer time. Address `bc1q66y45cq78ke25kz7rpe94l84avt7zetglzeeqg` (CHEN, Zhi), first listed 2025-10-30. Raw: `data/raw/utxo/btc1.trezor.io/06/06ceae7717d01867360ca67206d1a3ad34466ea47e18c793eb0da7c43041ff7a-4ca891501fdcd146.json.gz#response.transactions[2]`; price raw: `data/raw/prices/binance/BTC-1H/c418617f6cd1272991d0af7e8e08d7b41d99748ed248bfbdfe163cc2fa1c724c.json.gz#row=140;data/raw/prices/binance/USDT-HOURLY-FX-1H/19c80c11db891de4c2f25f956ae5c310ed03253a9736ea860341737abccaa36f.json.gz#row=852`.
- BTC [6c84d430e76f31e2659f25d996a9ad64adc861e2292279b8da7106820f1e42d4](https://mempool.space/tx/6c84d430e76f31e2659f25d996a9ad64adc861e2292279b8da7106820f1e42d4) — 2023-03-05T17:00:16Z; 0.99897028 native:BTC; 22422.05 USD at transfer time. Address `bc1q7des766x6c0zkycz6dz6rfv066n3fcg4kggtrt` (CHEN, Zhi), first listed 2025-10-30. Raw: `data/raw/utxo/btc1.trezor.io/47/47a3f40fb5c2fb24a8e21acd5499fdd3c8a6f9f907fcfd0a7144c37550637441-45f3b67949683adc.json.gz#response.transactions[0]`; price raw: `data/raw/prices/binance/BTC-1H/b72c2c8135143abc07a745371b586ee33488ac4ba367fd634239af382f38fcba.json.gz#row=232;data/raw/prices/binance/USDT-HOURLY-FX-1H/b604cf2ef8dd92cdeb9961296c057df3090851abea8ee63e738be0236138ca28.json.gz#row=85`.

### seven_day_depletion

**6.4044% share** — Share of observed, reconciled designation-date value net-depleted within seven days, excluding Tornado-associated identifiers.

Denominator: 491 addresses; 79 SDN UID entities; 4124244055.858519 USD at each address’s own T. Depleted value: 264133333.0538568 USD at the same T prices.

Confidence: Provisional observed subset, not all sanctioned crypto value. Mixed own-T prices. Replenishment can hide withdrawals; price changes cannot create depletion. Unknown/unreconciled balances excluded.

- ETH [0x6240848d80e7de9ac42fa16dd121f702bdf94183f05cda310adcb7a135ff9336](https://etherscan.io/tx/0x6240848d80e7de9ac42fa16dd121f702bdf94183f05cda310adcb7a135ff9336) — 2022-04-15T08:14:05Z; 2915.24 native:ETH; 8846645.61 USD at transfer time. Address `0x098b716b8aaf21512996dc57eb0615e2383e2f96` (LAZARUS GROUP), first listed 2022-04-14. Raw: `data/raw/evm/etherscan/f53be75d9098b9a5223f883c.json.gz#/response/result/354`; price raw: `data/raw/prices/binance/ETH-1H/e50227d4a3365189f0df89e2a5b1aa88b39f4fad806d5c7f36f61b86317ace77.json.gz#row=447;data/raw/prices/binance/USDT-HOURLY-FX-1H/7cc7028570b9a0916f25a54a9ab6808951b3f91a9666360d58a739fbd7837efe.json.gz#row=154`.
- ETH [0x7af5e2ce1d8f88c3a824d1569da4fc828965bb0a603e7951e739bf1764ba5374](https://etherscan.io/tx/0x7af5e2ce1d8f88c3a824d1569da4fc828965bb0a603e7951e739bf1764ba5374) — 2022-05-07T04:09:52Z; 3021.4 native:ETH; 8062966.70 USD at transfer time. Address `0x35fb6f6db4fb05e6a4ce86f2c93691425626d4b1` (LAZARUS GROUP), first listed 2022-05-06. Raw: `data/raw/evm/etherscan/52c7f709b632ddf175fcdc0a.json.gz#/response/result/5`; price raw: `data/raw/prices/binance/ETH-1H/e50227d4a3365189f0df89e2a5b1aa88b39f4fad806d5c7f36f61b86317ace77.json.gz#row=971;data/raw/prices/binance/USDT-HOURLY-FX-1H/7cc7028570b9a0916f25a54a9ab6808951b3f91a9666360d58a739fbd7837efe.json.gz#row=678`.
- ETH [0x8c92d82248ad2f0b1437b375f7b7e8e7777b41023a58dabb8c2ad1f7a6e26f62](https://etherscan.io/tx/0x8c92d82248ad2f0b1437b375f7b7e8e7777b41023a58dabb8c2ad1f7a6e26f62) — 2022-05-10T13:24:16Z; 3003.3 native:ETH; 7342274.21 USD at transfer time. Address `0xf7b31119c2682c88d88d455dbb9d5932c65cf1be` (LAZARUS GROUP), first listed 2022-05-06. Raw: `data/raw/evm/etherscan/ee2de15850ee3f174e0c87e4.json.gz#/response/result/4`; price raw: `data/raw/prices/binance/ETH-1H/50042aab94f245977e032861e84d5cce5656d2e03b6f932ca2c4443f73d1bdd3.json.gz#row=52;data/raw/prices/binance/USDT-HOURLY-FX-1H/7cc7028570b9a0916f25a54a9ab6808951b3f91a9666360d58a739fbd7837efe.json.gz#row=759`.

### largest_balances_today

**1078806439.1590044 usd** — Recognised-asset value currently observed at the ten largest listed non-Tornado chain-address pairs.

Valuation: each of the ten address latest fetched balance times; exact valuations in CSV.

Confidence: Direct saved latest-state observations; not proof funds are unfrozen, spendable or the original designation-date units. Same assets elsewhere excluded. Example transactions illustrate receipts, not the state balance itself.

- BTC [2f07391e3c91c70ccdd8b21d90216dc56e654668e40493f0090053dfe279a956](https://mempool.space/tx/2f07391e3c91c70ccdd8b21d90216dc56e654668e40493f0090053dfe279a956) — 2025-10-15T11:31:49Z; 4999.89896696 native:BTC; 561771624.65 USD at transfer time. Address `bc1qea942uw640l7nvtf3vplv6jd6wvuy06c58cd4k` (CHEN, Zhi), first listed 2025-10-30. Raw: `data/raw/utxo/btc1.trezor.io/f0/f0a0334962d7053fae8f91bd0be6863c8ffba012c9013163754168c48669033b-e012884eba39480a.json.gz#response.transactions[7]`; price raw: `data/raw/prices/binance/BTC-1H/c418617f6cd1272991d0af7e8e08d7b41d99748ed248bfbdfe163cc2fa1c724c.json.gz#row=145;data/raw/prices/binance/USDT-HOURLY-FX-1H/19c80c11db891de4c2f25f956ae5c310ed03253a9736ea860341737abccaa36f.json.gz#row=857`.
- TRX [d7c311f842a9b896bd8ad6c2e74247f949c29dba064fbd38aede9c1c3c264e8c](https://tronscan.org/#/transaction/d7c311f842a9b896bd8ad6c2e74247f949c29dba064fbd38aede9c1c3c264e8c) — 2023-01-22T21:09:09Z; 111000000 native:TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t; 111025038.35 USD at transfer time. Address `TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81` (BANK MARKAZI JOMHOURI ISLAMI IRAN), first listed 2026-04-24. Raw: `data/raw/tron/trc20/7cc6b8101728c5b751fd2699d1baa7df5f96d5081db5071208af0a91557ef6f9.json.gz#/response/data/163`; price raw: `data/raw/prices/coinmetrics/USDT-USDT-1D-0/3fe35e59e98b38f852dc24c015e9e0a970f9be6d8896afb373bbab4cd120d915.json.gz#row=3031`.
- TRX [bff00fbcb43e7b453b1ac0a32f5cb271656f8a90f3d40f85b63139c7842e6871](https://tronscan.org/#/transaction/bff00fbcb43e7b453b1ac0a32f5cb271656f8a90f3d40f85b63139c7842e6871) — 2021-08-04T18:59:12Z; 300 native:TRX; 20.23 USD at transfer time. Address `TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81` (BANK MARKAZI JOMHOURI ISLAMI IRAN), first listed 2026-04-24. Raw: `data/raw/tron/native/25ca4476be61dedfafbb22dc355305c4572aece0faeb6362bff636f7b7e1781b.json.gz#/response/data/2`; price raw: `data/raw/prices/binance/TRX-1H/534f3181068d165ac49b41b9c5d1514588ac9f985e2850bafd1aeed520001be3.json.gz#row=526;data/raw/prices/binance/USDT-HOURLY-FX-1H/0928889870929ffa44cc8b7908f62eef0c42f3d82bedbef2d1ae980c8fe029c1.json.gz#row=74`.

### empty_when_listed

**497 addresses** — Listed non-Tornado chain-address pairs with zero reconciled recognised-asset balance at T and an earlier non-dust outflow.

Confidence: Zero concerns recognised assets only; does not exclude unpriced tokens, off-address holdings or later deposits. Earlier movement does not imply knowledge of sanctions.

- BTC [a68bd5004d9c0ed77b9623c5ba58e3e79194b88f3ac191175db88f58908c1056](https://mempool.space/tx/a68bd5004d9c0ed77b9623c5ba58e3e79194b88f3ac191175db88f58908c1056) — 2025-07-22T03:40:54Z; 499.99999922 native:BTC; 58549034.33 USD at transfer time. Address `bc1qnq3pzsw3elkecrw8pqrz70r7zuse6cwyxa6dhc` (CHEN, Zhi), first listed 2025-10-30. Raw: `data/raw/utxo/btc1.trezor.io/98/980f8089a43f3b15b01960c7f79caa82137d9dd536be3586fbc9c32db0dbb6ac-6b0bf39dbe61b0cc.json.gz#response.transactions[0]`; price raw: `data/raw/prices/binance/BTC-1H/d9b9bb9600cbfcc7edfe0de5e964a4be56491ae73da42d4944673770a59db9f6.json.gz#row=97;data/raw/prices/binance/USDT-HOURLY-FX-1H/a2ffc5a763b356a4f900e10cde6324e87c660aa291015b044a1fbad97997ca6e.json.gz#row=809`.
- BTC [3dbf21395abddf175bafc55fbeae3d3e958ec9fd1e207c18241916ee1de4da97](https://mempool.space/tx/3dbf21395abddf175bafc55fbeae3d3e958ec9fd1e207c18241916ee1de4da97) — 2023-03-05T20:34:12Z; 1797.50039955 native:BTC; 40274237.75 USD at transfer time. Address `bc1qw0pswznckx7s6tjmd2f5hrx4q6kc5nyrdxku50` (CHEN, Zhi), first listed 2025-10-30. Raw: `data/raw/utxo/mempool.space/23/235acb009a3cee46734f8716f322e530d8fa86a737f630c695c2b8457328ca89-bb8cafd59adb947c.json.gz#response[0]`; price raw: `data/raw/prices/binance/BTC-1H/b72c2c8135143abc07a745371b586ee33488ac4ba367fd634239af382f38fcba.json.gz#row=235;data/raw/prices/binance/USDT-HOURLY-FX-1H/b604cf2ef8dd92cdeb9961296c057df3090851abea8ee63e738be0236138ca28.json.gz#row=85`.
- BTC [ab7413e5bb8c474146005d1733df3a8da90c7b1a04ef8d50247554648f4764c1](https://mempool.space/tx/ab7413e5bb8c474146005d1733df3a8da90c7b1a04ef8d50247554648f4764c1) — 2025-10-15T06:10:22Z; 213.45331229 native:BTC; 24013380.16 USD at transfer time. Address `3FoD1f6Tfnq3s8MYHgJqFPWv9cUrtUdBSv` (CHEN, Zhi), first listed 2025-10-30. Raw: `data/raw/utxo/btc1.trezor.io/b5/b5e0e4105ac1ed6f0f10838465b09af4acf2549f1f942bd72e4ee68d19ec023b-3f7b7b15d99e3c87.json.gz#response.transactions[2]`; price raw: `data/raw/prices/binance/BTC-1H/c418617f6cd1272991d0af7e8e08d7b41d99748ed248bfbdfe163cc2fa1c724c.json.gz#row=140;data/raw/prices/binance/USDT-HOURLY-FX-1H/19c80c11db891de4c2f25f956ae5c310ed03253a9736ea860341737abccaa36f.json.gz#row=852`.

### retained_blacklisted_usdt

**483183895.9609318 usd** — USDT observed at 6 of the twenty largest non-Tornado listed chain-address pairs whose issuer blacklist was active at the end of saved event history.

Valuation: at each latest saved USDT balance observation; exact times in examples and CSV.

Confidence: Latest balances are not freeze-time amounts. Blacklist state is replayed from saved add/remove logs, not a new live contract call. This is context for retained value, not proof of original holdings, spendability of other assets, or a legal conclusion.

- TRX [ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe](https://tronscan.org/#/transaction/ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe) — issuer blacklist event 2026-04-23T12:02:36Z for `TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81` (BANK MARKAZI JOMHOURI ISLAMI IRAN). Latest USDT balance: 212922804.915554 token units; 212648681.34 USD valued at 2026-10-23T20:13:30.620333Z. Event raw: `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`; balance raw: `data/raw/tron/balances/419de3304164a98756f00b13aa1d5fd04bb7102ac5479b5ddf6a1cd4d393ff84-1792786410539311410.json.gz#/response/constant_result/0`; price raw: `data/raw/prices/coinmetrics/USDT-USDT-1D-0/7b5ded846098f77113a0a1b9e848d8cd93544d2b9a8b1c1e1d697e2b602411a4.json.gz#row=3`.
- TRX [295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a](https://tronscan.org/#/transaction/295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a) — issuer blacklist event 2026-04-23T12:02:36Z for `TTiDLWE6fZK8okMJv6ijg42yrH6W2pjSr9` (BANK MARKAZI JOMHOURI ISLAMI IRAN). Latest USDT balance: 131288801.972952 token units; 131119776.61 USD valued at 2026-10-23T20:29:07.423558Z. Event raw: `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`; balance raw: `data/raw/tron/balances/afbd5392ac1f922ebe072e870bb6a529942a8c0424ed864b78d9d4cea103e50f-1792787347301772600.json.gz#/response/constant_result/0`; price raw: `data/raw/prices/coinmetrics/USDT-USDT-1D-0/7b5ded846098f77113a0a1b9e848d8cd93544d2b9a8b1c1e1d697e2b602411a4.json.gz#row=3`.
- TRX [005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4](https://tronscan.org/#/transaction/005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4) — issuer blacklist event 2026-07-14T21:02:57Z for `TFQbqaNbmq2xsVor2NbufLkYZvxFC9wC7k` (BANK MARKAZI JOMHOURI ISLAMI IRAN). Latest USDT balance: 85527016 token units; 85416905.81 USD valued at 2026-10-23T20:01:10.333874Z. Event raw: `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz`; balance raw: `data/raw/tron/balances/061b4dfaa13718ee85f1eb37e4420b9b8f268e02454b771eb96c364227a3b7fa-1792785670199349626.json.gz#/response/constant_result/0`; price raw: `data/raw/prices/coinmetrics/USDT-USDT-1D-0/7b5ded846098f77113a0a1b9e848d8cd93544d2b9a8b1c1e1d697e2b602411a4.json.gz#row=3`.

### first_move_by_program

**2.383611111111111 days** — Conditional median first-outflow lag among observed FTO movers, the lowest program median with at least five eligible movers in this snapshot.

Denominator: 11 addresses with observed non-dust first outflows.

Confidence: Exploratory ranking, not a causal or population-wide speed estimate. Complete histories and priced non-dust movers only; non-movers excluded, programs overlap, and publication time is a noon ET estimate with up to 12 hours uncertainty.

- TRX [3c14872537d8a8d9083fbb1a6a48d67c3f9b0fbdb5c35eaa692f75edf9a23441](https://tronscan.org/#/transaction/3c14872537d8a8d9083fbb1a6a48d67c3f9b0fbdb5c35eaa692f75edf9a23441) — 2026-07-04T01:12:24Z; 95 native:TRX; 30.79 USD at transfer time. Address `TTrJwfL8SCSWBXWAPcZV8Pd5fZf1rznRhz` (ISIL KHORASAN), first listed 2026-07-01. Raw: `data/raw/tron/native/3e7377d25acfbe6cb59f8755331105ea053b3528eeaefd2667b293ed70fe9cc5.json.gz#/response/data/29`; price raw: `data/raw/prices/binance/TRX-1H/e918524d042aedd7be6628fcdb1a26d267a6e1c0985157b16f2abfc06d92e3e9.json.gz#row=582;data/raw/prices/binance/USDT-HOURLY-FX-1H/5f5dc056748f2d30677edf06bd3b3b9a4830e4d5f908fd4850bf65569aa46162.json.gz#row=135`.
- TRX [db558fbe96289547b244068a43726204d20a8a3309f72d374026d871ef6e306b](https://tronscan.org/#/transaction/db558fbe96289547b244068a43726204d20a8a3309f72d374026d871ef6e306b) — 2026-07-04T02:40:45Z; 8.14072 native:TRX; 2.63 USD at transfer time. Address `TWoRwYzsifrD79DHDpTHC8fq787MvH9Qro` (ISIL KHORASAN), first listed 2026-07-01. Raw: `data/raw/tron/native/fc0b5431bfc4550dee620167db11ee0ce98cb675402a88cbea976945ba37874d.json.gz#/response/data/134`; price raw: `data/raw/prices/binance/TRX-1H/e918524d042aedd7be6628fcdb1a26d267a6e1c0985157b16f2abfc06d92e3e9.json.gz#row=583;data/raw/prices/binance/USDT-HOURLY-FX-1H/5f5dc056748f2d30677edf06bd3b3b9a4830e4d5f908fd4850bf65569aa46162.json.gz#row=136`.
- TRX [dd86597ba3de051ac380a5a85854dae17f7c54283c944ff0621c47a6625e4ece](https://tronscan.org/#/transaction/dd86597ba3de051ac380a5a85854dae17f7c54283c944ff0621c47a6625e4ece) — 2026-07-02T20:06:36Z; 5 native:TRX; 1.59 USD at transfer time. Address `TDXBEozXRJy7eBYNCoqrDMRCx5QBN4jCCt` (ISIL KHORASAN), first listed 2026-07-01. Raw: `data/raw/tron/native/6acf5d7926b5e223872c3647a6b877bd654cbc91bea39dc1938630a79e83accd.json.gz#/response/data/69`; price raw: `data/raw/prices/binance/TRX-1H/e918524d042aedd7be6628fcdb1a26d267a6e1c0985157b16f2abfc06d92e3e9.json.gz#row=553;data/raw/prices/binance/USDT-HOURLY-FX-1H/5f5dc056748f2d30677edf06bd3b3b9a4830e4d5f908fd4850bf65569aa46162.json.gz#row=106`.

## Largest balances observed today

Listed non-Tornado chain-address pairs. USD at each asset’s saved latest observation time; see CSV for exact time and price. These are balances at the address, including frozen funds if present, not proof of spendability or retention of the original units.

| Chain | Address | OFAC name(s) | USD at latest observation |
|---|---|---|---:|
| BTC | `bc1qea942uw640l7nvtf3vplv6jd6wvuy06c58cd4k` | CHEN, Zhi | 406,285,006.25 |
| TRX | `TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 212,648,817.82 |
| BTC | `bc1q66y45cq78ke25kz7rpe94l84avt7zetglzeeqg` | CHEN, Zhi | 132,448,801.52 |
| TRX | `TTiDLWE6fZK8okMJv6ijg42yrH6W2pjSr9` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 131,119,852.60 |
| TRX | `TFQbqaNbmq2xsVor2NbufLkYZvxFC9wC7k` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 85,416,919.05 |
| BTC | `bc1qcx8vxxrld2s7qvz64qp75s3508rkzaxj65l60q` | CHEN, Zhi | 48,762,335.80 |
| TRX | `TJdgB1k6ot3f2nLuZug6D8eD3HavTmzmSK` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 30,938,485.98 |
| TRX | `TXGHxdYbGy574z5hBu4LNzq9NzjZQ9bhUf` | BANK MARKAZI JOMHOURI ISLAMI IRAN | 12,291,035.04 |
| TRX | `TWPma8xH48AEN93x2krdukV9e1j6sPsBeS` | XINBI GUARANTEE | 10,769,483.07 |
| BTC | `bc1q05aktddf9ce4p7hh3stgsf253m4vweu7nkhtmw` | WANG, Yunhe | 8,125,702.03 |

## Chain and program comparisons

These tables conservatively exclude every identifier listed under an OFAC name containing TORNADO, plus independently identified pool/router/proxy addresses, matching the pre-move reference. `tornado_contract` preserves the narrower role flag and `tornado_excluded` records this broader population rule. Exchange-scale addresses remain included here; JSON contains both scale scopes and the all-listed population. Program membership and SDN UIDs overlap; do not sum program rows. Untrackable is the ledger flag, retained even if a fetcher later found a route.

### Concentration sensitivity

| SDN UID | OFAC name | Share of observed 7d T-value denominator | 7d depletion share excluding that UID |
|---|---|---:|---:|
| 55505 | CHEN, Zhi | 63.38% | 17.49% |
| 27307 | LAZARUS GROUP | 20.26% | 0.02% |
| 4632 | BANK MARKAZI JOMHOURI ISLAMI IRAN | 11.50% | 7.24% |

### by_chain

| Group | Ledger status | Addresses | Entities | T balance known (addresses) | Moved after (addresses) | Received after (addresses) | 7d depletion share | First move median (days; movers n) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ARB | trackable | 1 | 1 | 1 | 0 | 0 | 0.00% | unknown; 0 |
| BCH | trackable | 7 | 4 | 7 | 1 | 1 | 0.00% | 96.865; 1 |
| BNB | trackable | 1 | 2 | 0 | 0 | 0 | unknown | unknown; 0 |
| BSC | trackable | 1 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| BSV | trackable | 1 | 1 | 1 | 0 | 0 | unknown | unknown; 0 |
| BTC | trackable | 535 | 66 | 532 | 38 | 37 | 0.02% | 22.698; 38 |
| BTG | untrackable | 1 | 1 | 1 | 0 | 0 | unknown | unknown; 0 |
| DASH | trackable | 5 | 4 | 5 | 0 | 0 | unknown | unknown; 0 |
| DOGE | trackable | 2 | 1 | 2 | 0 | 0 | 0.00% | unknown; 0 |
| ETC | trackable | 1 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| ETH | trackable | 125 | 48 | 113 | 23 | 21 | 31.44% | 4.403; 23 |
| ETH | untrackable | 1 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| LTC | trackable | 13 | 10 | 13 | 2 | 2 | unknown | 748.904; 2 |
| SOL | trackable | 4 | 3 | 0 | 0 | 1 | unknown | unknown; 0 |
| TRX | trackable | 341 | 51 | 327 | 33 | 40 | 0.00% | 26.739; 33 |
| XMR | untrackable | 12 | 4 | 0 | 0 | 0 | unknown | unknown; 0 |
| XRP | trackable | 1 | 1 | 1 | 1 | 1 | 0.00% | -0.411; 1 |
| XVG | trackable | 1 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| ZEC | trackable | 4 | 4 | 0 | 0 | 0 | unknown | unknown; 0 |

### by_program

| Group | Ledger status | Addresses | Entities | T balance known (addresses) | Moved after (addresses) | Received after (addresses) | 7d depletion share | First move median (days; movers n) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CAATSA - RUSSIA | trackable | 2 | 2 | 2 | 0 | 0 | 0.00% | unknown; 0 |
| CYBER2 | trackable | 396 | 27 | 384 | 33 | 32 | 0.38% | 78.763; 33 |
| CYBER2 | untrackable | 5 | 3 | 1 | 0 | 0 | unknown | unknown; 0 |
| CYBER3 | trackable | 6 | 3 | 6 | 0 | 0 | 0.00% | unknown; 0 |
| CYBER4 | trackable | 58 | 10 | 53 | 6 | 7 | 0.00% | 26.739; 6 |
| DPRK2 | trackable | 1 | 1 | 1 | 0 | 0 | unknown | unknown; 0 |
| DPRK3 | trackable | 55 | 6 | 51 | 13 | 7 | 31.47% | 7.713; 13 |
| DPRK4 | trackable | 67 | 5 | 65 | 1 | 0 | 0.00% | 87.450; 1 |
| ELECTION-EO13848 | trackable | 55 | 6 | 51 | 8 | 8 | 16.23% | 80.635; 8 |
| ELECTION-EO13848 | untrackable | 3 | 2 | 0 | 0 | 0 | unknown | unknown; 0 |
| FTO | trackable | 139 | 2 | 136 | 11 | 17 | 0.04% | 2.384; 11 |
| FTO | untrackable | 4 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| HRIT-IR | trackable | 15 | 1 | 12 | 1 | 0 | 1.10% | -0.082; 1 |
| IFSR | trackable | 31 | 7 | 28 | 4 | 7 | 0.00% | 7.313; 4 |
| ILLICIT-DRUGS-EO14059 | trackable | 150 | 19 | 147 | 16 | 5 | 26.00% | 7.961; 16 |
| ILLICIT-DRUGS-EO14059 | untrackable | 5 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| IRAN | trackable | 6 | 1 | 6 | 1 | 2 | 0.00% | 14.279; 1 |
| IRAN-EO13902 | trackable | 8 | 2 | 7 | 0 | 1 | 0.00% | unknown; 0 |
| IRGC | trackable | 16 | 4 | 16 | 1 | 2 | 0.00% | 14.279; 1 |
| NPWMD | trackable | 22 | 2 | 20 | 4 | 4 | 0.00% | 80.635; 4 |
| NPWMD | untrackable | 2 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| RUSSIA-EO14024 | trackable | 35 | 11 | 35 | 5 | 4 | 34.65% | 2.728; 5 |
| SDGT | trackable | 211 | 26 | 198 | 18 | 32 | 0.00% | 8.217; 18 |
| SDGT | untrackable | 4 | 1 | 0 | 0 | 0 | unknown | unknown; 0 |
| SDNTK | trackable | 12 | 3 | 12 | 2 | 11 | 0.00% | 256.955; 2 |
| TCO | trackable | 88 | 9 | 87 | 8 | 7 | 0.00% | 7.144; 8 |
| UKRAINE-EO13661 | trackable | 2 | 1 | 1 | 0 | 0 | unknown | unknown; 0 |

### tron_vs_everything_else

| Group | Ledger status | Addresses | Entities | T balance known (addresses) | Moved after (addresses) | Received after (addresses) | 7d depletion share | First move median (days; movers n) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tron | trackable | 341 | 51 | 327 | 33 | 40 | 0.00% | 26.739; 33 |
| everything_else | trackable | 702 | 81 | 675 | 65 | 63 | 7.35% | 7.819; 65 |
| everything_else | untrackable | 14 | 5 | 1 | 0 | 0 | unknown | unknown; 0 |

## Method and limits

- **T:** 00:00 America/New_York on the first publication date; T balance excludes transactions at or after T
- **T_pub:** 12:00 America/New_York; first outflow is first >=T, lag against T_pub may be negative on the designation morning
- **checkpoints:** T-7d, T, T+7d, T+30d, T+365d use ET calendar dates; future or uncovered endpoints are null; today is each latest saved state
- **depletion:** sum_asset(max(0, balance_T - balance_checkpoint) * price_T) / sum_asset(balance_T * price_T); no lot tracing; recognised priced assets only
- **balances:** from-zero signed transfer amounts minus fees, only on complete histories that reconcile per asset with current saved state; today's direct observations remain usable on incomplete histories
- **prices:** scripts/prices/price.py usd(); checkpoint time or transfer time. WETH/ETH, WBTC/BTC, and BSC pegged USDT/USDC use underlying-price proxies, not independent wrapper market quotes
- **dust_and_spam:** recognised-contract/native transfers >=1 USD at transfer time; unknown contracts and zero amounts excluded. Unknown asset native quantities remain in CSV, never valued from ticker
- **inflows:** total_inflow_after_usd covers non-dust recognised assets only; partial/unpriced recognised histories return null plus a priced subtotal
- **first_outflow_median:** conditional on observed non-dust movers with complete history and prices, not population survival time; non-movers are censored
- **entities:** distinct SDN UIDs in each row/group, not persons or independent wallets; groups/programs overlap and must not be added
- **same_address_other_chain:** separate view, anchored at the earliest publication of the same 0x string on a listed EVM chain; excluded from listed-chain aggregates
- **untrackable:** ledger trackable flag preserved, shown in separate rows even where a fetcher later found a working route (e.g. BTG)
- **exchange_scale:** more than 10,000 distinct observed transaction hashes, or fetcher huge_address/reported_history_records >10,000; incomplete lower-count histories may conceal scale
- **tornado_exclusion:** primary population excludes all identifiers under an OFAC name containing TORNADO, plus independently identified pool/router/proxy addresses; matches the pre-move reference. tornado_contract retains the narrower role flag; tornado_excluded records the broader population rule
- **provisional:** completed bounded acquisition; the manifest hashes identify this read pass, not a simultaneous multi-chain snapshot

All value totals are recognised-asset subtotals, not an estimate of unpriced holdings. Unknown/spam token quantities remain unvalued. From-zero reconstruction and a matching latest state are necessary checks, not proof of indexer completeness or absence of offsetting omissions. A stablecoin issuer burn can change state without a Transfer event; mismatches are not attributed to withdrawals. Per-asset reconciliation failure suppresses its historical checkpoints. A full-address recognised-asset total is null if a recognised asset is missing, even when other assets are known.

Ethereum Tornado pools have separately scoped event/daily archive data: whole-address coverage.complete is false, so this script leaves historical checkpoints unknown rather than presenting daily samples as midnight balances. BSC/Base and unavailable-chain stubs have explicit history gaps. Tron staking/reward/resource changes may prevent native reconciliation; native-coin failure does not invalidate a separately reconciled USDT asset, but does suppress the full recognised-asset address total. Solana token-account discovery remains incomplete. BNB Beacon snapshots are legacy state, not evidence of current spendability or BSC recovery holdings. See `docs/COVERAGE.md` and `docs/sources/{EVM,TRON,UTXO,PRICES}.md` for source-specific limits.

Post-T observations run through the latest fetched head, including periods after any delisting. They are “after first publication,” not a statement that an address remained sanctioned throughout. Future T+365d checkpoints remain unknown. Comparisons across checkpoints can use different eligible cohorts; each JSON depletion cell reports its own address/entity/USD denominator.

New relative to the prior Ethereum and Bitcoin papers: one consistent chain-address table across listed chains, a separately labelled other-EVM-chain view, recognised-token/native per-asset reconciliation, and program/year/Tron and scale sensitivities. This bounded snapshot is not a complete cross-chain population estimate.
