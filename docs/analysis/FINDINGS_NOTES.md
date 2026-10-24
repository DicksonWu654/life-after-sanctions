# Findings: evidence and interpretation

Data as of **2026-10-23**. All seven published result summaries mark acquisition `provisional: false`; that status does not imply complete chain or asset coverage. [FINDINGS](../../FINDINGS.md) records the observations and their denominators. Full producer checks need raw evidence and normalized histories; `make verify` validates the public saved-data snapshot.

## Independent freeze lower bound

The independent audit establishes **at least 529,064,435.426376 native USDT at first freeze**, from its original **334/341-address known-balance cohort**. Seven first-freeze balances were unknown in that frozen audit cohort. This is not a verified all-address total or one simultaneous balance. Its publication wording is **at least 529 million USDT**, not “529 million held by all 341 addresses.”

The audit closes transfer-coverage checks for 304/334 claimed-known histories; other captured balances reproduce the archived source responses but lack independently proven pagination continuity. The price-proxy equivalent is 529,081,410.568 USD, valued_at each first-freeze UTC date using that date’s daily Coin Metrics price label, not at the freeze second. FINDINGS uses native units for issuer-held quantities.

The rebuilt results/freeze_match.json now separately reports 531,209,975.485103 native USDT over **339** known first-freeze balances, with two unknown. It is a later expanded reconstruction, not the independently checked original 334-address subtotal. Do not substitute the 339-address count into the audit claim, or label the later subtotal independently verified in full.

The independently verified original subtotal and 334-address cohort have no matching scalar result target in results/*.json. FINDINGS therefore uses a clearly distinguished audit-check tag for this independent CSV source, rather than pretending that the later JSON subtotal is the audit figure. The findings checker recomputes the original subtotal and the known/total/unknown address counts from the verification CSV; all four audit tags are exact and every analysis number retains the requested results-JSON tag. This narrow source-format exception is explicit in FINDINGS. Source: docs/verify/FREEZE_VERIFY.md, data/verify/freeze_verify.csv and data/raw/verify_freeze/claim_baseline.json.gz.


## BANK MARKAZI JOMHOURI ISLAMI IRAN: full Tron cohort

Joined the derived freeze rows to the exact OFAC name/UID, and checked that the six TRX addresses in results/freeze_match.json#summary.146 (issuer tether, program IRAN, variant all, year ALL) are exactly that name’s listed Tron identifiers. This is not an assumption that the broader IFSR or IRGC program is a bank-only cohort.

Native first-freeze sum: **474,308,691.678231 USDT across six addresses**. Two first freezes occurred before the listing day began; their subtotal is **344,211,454.458506 USDT**. The other four events were on their listing day, so the unknown intraday OFAC timestamp prevents a before/after publication assertion. The bank sum agrees with the independently reconstructed six address rows in the freeze audit.

| Address | First-freeze USDT | First-freeze UTC | Pre-listing day? | raw_ref |
|---|---:|---|---|---|
| `TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81` | 212922653.485554 | 2026-04-23T12:02:36Z | yes | `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz` |
| `TTiDLWE6fZK8okMJv6ijg42yrH6W2pjSr9` | 131288800.972952 | 2026-04-23T12:02:36Z | yes | `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz` |
| `TFQbqaNbmq2xsVor2NbufLkYZvxFC9wC7k` | 85527016.0 | 2026-07-14T21:02:57Z | same day; order unknown | `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz` |
| `TJdgB1k6ot3f2nLuZug6D8eD3HavTmzmSK` | 30978224.260461 | 2026-07-14T21:02:57Z | same day; order unknown | `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz` |
| `TXGHxdYbGy574z5hBu4LNzq9NzjZQ9bhUf` | 12306816.47787 | 2026-07-14T21:02:57Z | same day; order unknown | `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz` |
| `TAhwhFv3JpK39Nc2m8W5LPCcoTisutiRfp` | 1285180.481394 | 2026-07-14T21:02:57Z | same day; order unknown | `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz` |


## Movement is not issuer freezing: two different sets of 96

The site export was inspected read-only. Its moved_before_designation=true set exactly equals the current checkpoint moved_before=true set, by chain and address: 96 addresses, with no set differences. The original equality of counts therefore does **not** show that the exporter used the issuer-freeze count.

| Quantity | Addresses | Denominator / scope | raw_ref |
|---|---:|---|---|
| Checkpoint pre-listing-week qualifying outflow | 96 | 1,134 trackable listed chain-address pairs, including Tornado-associated identifiers | results/checkpoints.json#aggregates.overall.0 |
| Same checkpoint flag excluding Tornado cohort | 81 | 1,043 trackable non-Tornado chain-address pairs | results/checkpoints.json#headline_population |
| Registered pre-move primary test, active pre-week | 49 | 887 eligible non-Tornado addresses with complete histories and sufficient baseline weeks | results/premove.json#candidate_findings.0 |
| Tether first blacklist before listing day began | 96 | 341 Tron listed addresses | results/freeze_match.json#summary.112 |
| Intersection: pre-week movement and early Tron freeze | 35 | Set intersection, not an additional population | scripts/analysis/findings_check.py#movement_reconciliation; data/derived/freeze_match.csv |
| Movement only / early freeze only | 61 / 61 | Distinct set differences | scripts/analysis/findings_check.py#movement_reconciliation; data/derived/freeze_match.csv |

The 96 pre-week movers break down as TRX 48, BTC 25, ETH 21, XRP 1 and LTC 1. The issuer-timing set is entirely TRX. The primary test’s 49 active addresses are all contained in the non-Tornado checkpoint set; it excludes addresses failing the full-history/baseline eligibility rules. Its active-address breakdown is BTC 20, ETH 4, TRX 23, XRP 1 and LTC 1. The 81 versus 49 difference is thus a cohort/eligibility difference, not a different kind of freeze.

The primary observed share is 49/887 = 5.52423900789177%, versus the mean own-baseline weekly share of 15.349734844775315%. The Holm-adjusted one-sided p value for excess is 1.0. Neither that result nor the lower descriptive activity share proves absence of individual advance notice.

Both the inspected site export and checkpoint result contain zero negative first-post-listing lags. This is compatible with pre-listing activity: checkpoints.analyze selects events[before] from [T-7d,T), separately selects events[after] from [T,infinity), and defines first_outflow_lag_days only from events[after], against noon ET. moved_before describes an earlier event; first_outflow_days does not describe that event. The exporter additionally retains publication-day uncertainty via publication_lag and may suppress same-day point lags when the full-day interval crosses zero.

Source boundaries: scripts/analysis/checkpoints.py analyze(); scripts/analysis/premove.py registered eligibility and primary shift_0_window_7; scripts/export_site.py observed-summary assignment and publication_lag(). No edit to scripts/export_site.py was made. The numerical set reconciliation is now implemented in our owned findings_check.py and runs with the editorial validation.


## Plain CHEN, Zhi finding

CHEN, Zhi-listed identifiers account for 1,722,913,707.055637 USD of observed post-listing gross output value, valued_at each constituent transfer’s historical price observation. The observed wallet denominator is 2,489,419,653.782674 USD at the same per-transfer valuation convention. The cited public account reports a DOJ forfeiture and government custody alongside the listing. It does not name the recipients of these particular on-chain transfers.

FINDINGS now says that the largest post-listing outflows coincide with that forfeiture/custody context. It does not infer who controls the recipient addresses, call the transfers evasion, or claim that gross turnover is unique wealth. Raw transactions and the saved TRM context source remain linked with the finding.


## Current source inventory

Each source was read locally. Full JSON loading resolves every quantitative equality target; input hashes identify the exact rebuilt files used. Dates, hashes, paths and observation timestamps are metadata rather than scalar amount claims.

| raw_ref | SHA-256 | Bytes |
|---|---|---:|
| `results/cases.json` | `1721aedc8db97ff9111a62ed605ed81080cc7b20552e0a79c4bdea6962d67a9b` | 1989981 |
| `results/checkpoints.json` | `0d9c39820f17d2c3db7335c9991c28675130c75fe30e951aea5eb673773fc362` | 4230446 |
| `results/flows.json` | `d3d6e2a5d23cec5d13ed62705a1b79b93a101d5f8fa7445770e3faa29a696099` | 197846 |
| `results/freeze_match.json` | `6814facde644aea363782ef49e195fca9423f348bac1c217bffb6dd4127ea452` | 932866 |
| `results/inflows.json` | `59022c36f6ff550fe7fcc217b975b3bf4fadd11b7b221c55fb951b4f684beb49` | 3366836 |
| `results/premove.json` | `fb559b760d4ba7bdf99eae29033bc077f8b139dadf590893f5a60f624215d315` | 31094902 |
| `results/tornado.json` | `5ab7d1dbc8f82f8405782cf6efc0ed0f255eda26f5d7f1736cede1abb201789e` | 1986516 |
| `docs/analysis/CASES.md` | `1fddeef4974b1b1617d990dd4744ae981b7ffc667f5949089ce3b1ec8a601995` | 333709 |
| `docs/analysis/CHECKPOINTS.md` | `9695e7552cc20f46e584a6be6b4901025fc0ea75310c9717e44897dcc8628295` | 30933 |
| `docs/analysis/FLOWS.md` | `792e45dbf67e69588b4edc8390319bb4cdce510ea2d5bc213b44763afaa72efd` | 23712 |
| `docs/analysis/FREEZE_MATCH.md` | `d30a915712affd3ea8a96b9cba35b71cf40d0f749fec74ab7b0693f89cff2a27` | 41229 |
| `docs/analysis/INFLOWS.md` | `6b435a9c78b68736ccf00f8e4442bde679d35e0796861c14a9bf2208c3571e1e` | 28907 |
| `docs/analysis/PREMOVE.md` | `ff60d25a83b85bb7dca743c03f66e6588ebbb5ef1e54c853f8367441ce5980ee` | 49438 |
| `docs/analysis/TORNADO.md` | `2d560dc568f2d82265cc23f7eeeff4a9ed42bcdb5e149820fe5511d4ddfda4ca` | 25130 |
| `docs/PRIOR_ART.md` | `b3063e329b4e50089fa139e89ea219d840b026103f921aed4b86021d5b9a5abd` | 36421 |
| `docs/DEFINITIONS.md` | `9179dbd733e062f7b33598494b087620638fbe38a6a9bd3abd24ee3107119303` | 2831 |
| `docs/COVERAGE.md` | `70501dbba2155bc5e38e444d8e4b71b00fbbd477c8c9eb68cbc16cc052964389` | 25463 |
| `docs/verify/FREEZE_VERIFY.md` | `ff611aac0b9d9b900942570686436815a2e8559f4f71b810e35c0a6ca47355bf` | 13322 |
| `data/verify/freeze_verify.csv` | `d336b69e79f22e4d5d0c552876211412fae043cd2a84cb8412e31bb4222007bb` | 881130 |


## Linked transaction evidence

The checker opens every raw envelope, resolves its pointer, requires saved request metadata, verifies a transaction-hash field and checks the explorer URL. The following is an evidence index, not an independent random sample of aggregate accuracy.

### Tether froze 474,308,691.68 USDT across BANK MARKAZI JOMHOURI ISLAMI IRAN’s listed Tron addresses.

- [ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe](https://tronscan.org/#/transaction/ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe) — raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`; saved request endpoint `https://api.trongrid.io/v1/contracts/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t/events`.
- [295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a](https://tronscan.org/#/transaction/295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a) — raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`; saved request endpoint `https://api.trongrid.io/v1/contracts/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t/events`.
- [005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4](https://tronscan.org/#/transaction/005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4) — raw `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz`; saved request endpoint `https://api.trongrid.io/v1/contracts/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t/events`.

### Tether blacklisted all 341 OFAC-listed Tron addresses.

- [344407805efd031c4bd1194969da21fe6ec655d93dad2ca66ef3ccede473765b](https://tronscan.org/#/transaction/344407805efd031c4bd1194969da21fe6ec655d93dad2ca66ef3ccede473765b) — raw `data/raw/freezes/tron_events/8500c77166a42f01eccc2f68d18df4c2dc188c5889b26c0b80e8c6a9e8c59ad4.json.gz`; saved request endpoint `https://api.trongrid.io/v1/contracts/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t/events`.
- [ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe](https://tronscan.org/#/transaction/ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe) — raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`; saved request endpoint `https://api.trongrid.io/v1/contracts/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t/events`.
- [295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a](https://tronscan.org/#/transaction/295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a) — raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`; saved request endpoint `https://api.trongrid.io/v1/contracts/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t/events`.

### 497 listed addresses had already sent funds out and held no measured balance when OFAC listed them.

- [a68bd5004d9c0ed77b9623c5ba58e3e79194b88f3ac191175db88f58908c1056](https://mempool.space/tx/a68bd5004d9c0ed77b9623c5ba58e3e79194b88f3ac191175db88f58908c1056) — raw `data/raw/utxo/btc1.trezor.io/98/980f8089a43f3b15b01960c7f79caa82137d9dd536be3586fbc9c32db0dbb6ac-6b0bf39dbe61b0cc.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1qnq3pzsw3elkecrw8pqrz70r7zuse6cwyxa6dhc`.
- [3dbf21395abddf175bafc55fbeae3d3e958ec9fd1e207c18241916ee1de4da97](https://mempool.space/tx/3dbf21395abddf175bafc55fbeae3d3e958ec9fd1e207c18241916ee1de4da97) — raw `data/raw/utxo/mempool.space/23/235acb009a3cee46734f8716f322e530d8fa86a737f630c695c2b8457328ca89-bb8cafd59adb947c.json.gz#response[0]`; saved request endpoint `https://mempool.space/api/address/bc1qw0pswznckx7s6tjmd2f5hrx4q6kc5nyrdxku50/txs/chain`.
- [ab7413e5bb8c474146005d1733df3a8da90c7b1a04ef8d50247554648f4764c1](https://mempool.space/tx/ab7413e5bb8c474146005d1733df3a8da90c7b1a04ef8d50247554648f4764c1) — raw `data/raw/utxo/btc1.trezor.io/b5/b5e0e4105ac1ed6f0f10838465b09af4acf2549f1f942bd72e4ee68d19ec023b-3f7b7b15d99e3c87.json.gz#response.transactions[2]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/3FoD1f6Tfnq3s8MYHgJqFPWv9cUrtUdBSv`.

### Tornado Cash’s ETH deposits rose 154.70% after OFAC removed its designation.

- [0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec](https://etherscan.io/tx/0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec) — raw `data/raw/evm/rpc/768a90a0e23a5b4cd0bfbe4b.json.gz#/response/result/1370`; saved request endpoint `https://rpc.mevblocker.io`.
- [0xf90c405ae2b8fb2cde2b46da5a5a01c5ad2ddb46b5cecaed4f9d03a41537b9bf](https://etherscan.io/tx/0xf90c405ae2b8fb2cde2b46da5a5a01c5ad2ddb46b5cecaed4f9d03a41537b9bf) — raw `data/raw/evm/rpc/6e2e217738416be11ab3ca36.json.gz#/response/result/3249`; saved request endpoint `https://rpc.mevblocker.io`.
- [0x5d93a2e859d897eefa3ecf94fe24d285f289077eb5b734f16ae67a17ae2c7662](https://etherscan.io/tx/0x5d93a2e859d897eefa3ecf94fe24d285f289077eb5b734f16ae67a17ae2c7662) — raw `data/raw/evm/rpc/89dd4c4962c92eb868d0fd94.json.gz#/response/result/3310`; saved request endpoint `https://rpc.mevblocker.io`.

### The largest post-listing outflows coincide with a DOJ forfeiture and government custody.

- [c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24](https://mempool.space/tx/c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24) — raw `data/raw/utxo/btc1.trezor.io/0a/0ad65fa1eecd9b209198c537739f4f12fe9e3841bd672431f8e48462a93278d1-d431f26e91059872.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1qeth6n6ryxexvkx34wnx3nuynun4474h3j0gkhw`.
- [b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885](https://mempool.space/tx/b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885) — raw `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1q2we5eqjj8je6lz9xwjattpc3pn4jejc5h0s70f`.
- [e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d](https://mempool.space/tx/e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d) — raw `data/raw/utxo/btc1.trezor.io/ad/ad5196fbd51b3e7b5f6e8ef2ae314eae2fde8fd1c61273837db96e3f1ee6c77f-a9cff8ff8e5389c8.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1qw4fxztd5u3sl7vrcqwk2a8v5zh5dllvckx3tlt`.

### Addresses moved funds less often in the week before listing than in their own baseline weeks.

- [280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53](https://mempool.space/tx/280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53) — raw `data/raw/utxo/btc1.trezor.io/2f/2f75728ccb6c1932ce21fa57d5832a350b1c351d46a040893d5bdc2b0a317acb-fa713d0510841727.json.gz#response.transactions[78]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/3P6PzdfETr4275Gn3veLkCyDxA1jV8fHKm`.
- [e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b](https://tronscan.org/#/transaction/e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b) — raw `data/raw/tron/trc20/2c30dd9f719931271b4cd26fc98490482e95ef0e72863a5d9c8c5cb8eb0d6134.json.gz#/response/data/41`; saved request endpoint `https://api.trongrid.io/v1/accounts/TAQPzv9941nVuTj4ng2vd6L11Re57r42pW/transactions/trc20`.
- [c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73](https://tronscan.org/#/transaction/c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73) — raw `data/raw/tron/trc20/9a35ecf99419525c870fcfc081eef8353f1bfeb4116056cff4d07100a14f378f.json.gz#/response/data/25`; saved request endpoint `https://api.trongrid.io/v1/accounts/TXEaKf4rT3rMoD3Vuqnuhwr6vLq6BL5t33/transactions/trc20`.

### Measured designation-date balances shrank by 6.40% within a week.

- [0x6240848d80e7de9ac42fa16dd121f702bdf94183f05cda310adcb7a135ff9336](https://etherscan.io/tx/0x6240848d80e7de9ac42fa16dd121f702bdf94183f05cda310adcb7a135ff9336) — raw `data/raw/evm/etherscan/f53be75d9098b9a5223f883c.json.gz#/response/result/354`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0x7af5e2ce1d8f88c3a824d1569da4fc828965bb0a603e7951e739bf1764ba5374](https://etherscan.io/tx/0x7af5e2ce1d8f88c3a824d1569da4fc828965bb0a603e7951e739bf1764ba5374) — raw `data/raw/evm/etherscan/52c7f709b632ddf175fcdc0a.json.gz#/response/result/5`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0x8c92d82248ad2f0b1437b375f7b7e8e7777b41023a58dabb8c2ad1f7a6e26f62](https://etherscan.io/tx/0x8c92d82248ad2f0b1437b375f7b7e8e7777b41023a58dabb8c2ad1f7a6e26f62) — raw `data/raw/evm/etherscan/ee2de15850ee3f174e0c87e4.json.gz#/response/result/4`; saved request endpoint `https://api.etherscan.io/v2/api`.

### Tornado Cash makes Tether’s Ethereum freeze lag look far slower than its wallet-only lag.

- [0x3c0978677bac14d4dd33b1b3ed4badfd4e03416fce640e23b273366f60945fc4](https://etherscan.io/tx/0x3c0978677bac14d4dd33b1b3ed4badfd4e03416fce640e23b273366f60945fc4) — raw `data/raw/freezes/logs/0fbe6c7324bfb44c48358c58802ca608dbc1346054eb55b67cb806c702177884.json.gz`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0xb993aa7b35cd6278b10bec5ab86a9b1fbaa5f0e6b68e6843dd57d09fde963ea4](https://etherscan.io/tx/0xb993aa7b35cd6278b10bec5ab86a9b1fbaa5f0e6b68e6843dd57d09fde963ea4) — raw `data/raw/freezes/logs/0fbe6c7324bfb44c48358c58802ca608dbc1346054eb55b67cb806c702177884.json.gz`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0x5906c3dac2d75f141b72baa61842a9881e9d31ee36f761ffc7059ffc86c7e452](https://etherscan.io/tx/0x5906c3dac2d75f141b72baa61842a9881e9d31ee36f761ffc7059ffc86c7e452) — raw `data/raw/freezes/logs/d221629fdcfabd20b31627d3ffb24d92f23e1ee8da99492e0cddd93b67b5480b.json.gz`; saved request endpoint `https://api.etherscan.io/v2/api`.

### The biggest observed qualifying receipt moved between addresses listed under the same OFAC name.

- [0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73](https://etherscan.io/tx/0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73) — raw `data/raw/evm/etherscan/e50db83fbf6fcb8b69607a0b.json.gz#/response/result/49`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32](https://etherscan.io/tx/0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32) — raw `data/raw/evm/etherscan/3d9dd1d54e3a3425194382f8.json.gz#/response/result/60`; saved request endpoint `https://api.etherscan.io/v2/api`.

### Only 329 incoming transfers passed the study’s value and token filters during listing periods.

- [0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000](https://etherscan.io/tx/0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000) — raw `data/raw/evm/etherscan/261226a12b77f3a7ba615e4e.json.gz#/response/result/76`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06](https://tronscan.org/#/transaction/faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06) — raw `data/raw/tron/native/d417c27b9007ecf1e0b758674bef24089d1bcf885e09f1bee07b47c9ed0695cd.json.gz#/response/data/164`; saved request endpoint `https://api.trongrid.io/v1/accounts/TWBAPzpPiZarfVsY2BLXeaLhNHurn4wkWG/transactions`.
- [0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f](https://etherscan.io/tx/0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f) — raw `data/raw/evm/etherscan/f4c62957d25cb844679c5b0e.json.gz#/response/result/71`; saved request endpoint `https://api.etherscan.io/v2/api`.

### Tornado Cash’s classic ETH pools now hold more ETH than at the paper’s delisting-period endpoint.

- [0x650311f3a8854bdd5ddbead3720d26d6cc9146fc71cbe7c8c271b2c0a8523b3a](https://etherscan.io/tx/0x650311f3a8854bdd5ddbead3720d26d6cc9146fc71cbe7c8c271b2c0a8523b3a) — raw `data/raw/evm/rpc/55146e0675bf985bdfc508cc.json.gz#/response/result/7860`; saved request endpoint `https://rpc.mevblocker.io`.
- [0x38c7d6896950a89ae0336991ea065f8dffb238e8edd062c4fe745b13310b50d3](https://etherscan.io/tx/0x38c7d6896950a89ae0336991ea065f8dffb238e8edd062c4fe745b13310b50d3) — raw `data/raw/evm/rpc/97a6dd75a814d4f37e421dc0.json.gz#/response/result/4667`; saved request endpoint `https://rpc.mevblocker.io`.
- [0x956dfbfd35c79aadcf7f57c376fdc2a6461aa09e87b77b93ed7c9b11a5e63532](https://etherscan.io/tx/0x956dfbfd35c79aadcf7f57c376fdc2a6461aa09e87b77b93ed7c9b11a5e63532) — raw `data/raw/evm/rpc/ebe5aeb76746f965031aec65.json.gz#/response/result/8083`; saved request endpoint `https://rpc.mevblocker.io`.

### Tornado Cash’s native-ETH deposit change around its initial designation was −67.96%.

- [0x39e477e177999a8f879ef4505c9fa8df1549b24cc5be946959b532f7632ce182](https://etherscan.io/tx/0x39e477e177999a8f879ef4505c9fa8df1549b24cc5be946959b532f7632ce182) — raw `data/raw/evm/rpc/3555e075d4a469d7e8863ed9.json.gz#/response/result/7250`; saved request endpoint `https://rpc.mevblocker.io`.
- [0x3b9f1a2628a2652408ee7f6ee2a6221e712f19bd007e1f32250bf1d87b9253e7](https://etherscan.io/tx/0x3b9f1a2628a2652408ee7f6ee2a6221e712f19bd007e1f32250bf1d87b9253e7) — raw `data/raw/evm/rpc/d1f6c7cf92de96a7a4171f35.json.gz#/response/result/2821`; saved request endpoint `https://rpc.mevblocker.io`.
- [0x780302391733404241d454c518859fad508e09146b52b8e416fedd2c5c8b1a70](https://etherscan.io/tx/0x780302391733404241d454c518859fad508e09146b52b8e416fedd2c5c8b1a70) — raw `data/raw/evm/rpc/0532eda0fbbc1ce02c3591d6.json.gz#/response/result/4345`; saved request endpoint `https://rpc.mevblocker.io`.

### 98.83% of incoming records were dust or operational spam under the study’s rules.

- [0x0a094420b6ffe21698776a4dc5a2566c6d82ff8efcb9576016b5061ae4a53c60](https://etherscan.io/tx/0x0a094420b6ffe21698776a4dc5a2566c6d82ff8efcb9576016b5061ae4a53c60) — raw `data/raw/evm/etherscan/e89c4bb956b6d333ee51d5a3.json.gz#/response/result/37`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0xd33ef30ec1599aa18e14db9de153659d01c336c6e828eaadc559d62d8c793480](https://etherscan.io/tx/0xd33ef30ec1599aa18e14db9de153659d01c336c6e828eaadc559d62d8c793480) — raw `data/raw/evm/etherscan/3d9dd1d54e3a3425194382f8.json.gz#/response/result/63`; saved request endpoint `https://api.etherscan.io/v2/api`.
- [0x1b25e6ad8a3344a18a23cffeda2759e8e7d7848115d7196045a5cff0ad2c77fa](https://etherscan.io/tx/0x1b25e6ad8a3344a18a23cffeda2759e8e7d7848115d7196045a5cff0ad2c77fa) — raw `data/raw/evm/etherscan/f53be75d9098b9a5223f883c.json.gz#/response/result/429`; saved request endpoint `https://api.etherscan.io/v2/api`.

### Public service labels leave 99.85% of measured first-hop outflow value unclassified.

- [c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24](https://mempool.space/tx/c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24) — raw `data/raw/utxo/btc1.trezor.io/0a/0ad65fa1eecd9b209198c537739f4f12fe9e3841bd672431f8e48462a93278d1-d431f26e91059872.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1qeth6n6ryxexvkx34wnx3nuynun4474h3j0gkhw`.
- [b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885](https://mempool.space/tx/b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885) — raw `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1q2we5eqjj8je6lz9xwjattpc3pn4jejc5h0s70f`.
- [e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d](https://mempool.space/tx/e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d) — raw `data/raw/utxo/btc1.trezor.io/ad/ad5196fbd51b3e7b5f6e8ef2ae314eae2fde8fd1c61273837db96e3f1ee6c77f-a9cff8ff8e5389c8.json.gz#response.transactions[0]`; saved request endpoint `https://btc1.trezor.io/api/v2/address/bc1qw4fxztd5u3sl7vrcqwk2a8v5zh5dllvckx3tlt`.

