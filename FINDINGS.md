# Life After Sanctions — candidate findings

Updated editorial draft using the completed acquisition and rebuilt analysis snapshot, ordered for surprise and shareability. Every results file now declares `provisional: false`; the documented chain, asset and reconciliation gaps remain. First listing means publication of the address identifier, rather than the entity’s original designation. Wallet findings exclude the Tornado-associated identifier cohort unless stated. These are observations within the data checked, not causal estimates of sanctions’ effects.

USD figures below state `valued_at`; native USDT and ETH quantities are not dollars. The qualifying-inflow filter uses recognized assets and the threshold recorded in `results/inflows.json#rules.real`; its word “real” describes a rule, not a known payment purpose. Transaction examples illustrate the stated cohort; aggregate balances require the accompanying state/history evidence.

The explicit-value annotations are validated offline by `scripts/analysis/findings_check.py --check`. Snapshot hashes, the independent freeze adjustment, the movement-versus-freeze reconciliation and raw-request evidence are in [FINDINGS_NOTES](docs/analysis/FINDINGS_NOTES.md). [Prior art](docs/PRIOR_ART.md), [definitions](docs/DEFINITIONS.md), [coverage](docs/COVERAGE.md) and the [independent freeze audit](docs/verify/FREEZE_VERIFY.md) govern interpretation. This is research, not legal or compliance advice; receipt from a listed address does not establish wrongdoing.

## Tether froze 474,308,691.68 USDT across BANK MARKAZI JOMHOURI ISLAMI IRAN’s listed Tron addresses.
<!-- check: results/freeze_match.json#summary.146.frozen_native_known_subtotal.value = 474308691.678231 -->

Denominator: **6 listed Tron addresses**, all under OFAC’s name BANK MARKAZI JOMHOURI ISLAMI IRAN. Each has a reconstructed first-freeze balance.
<!-- check: results/freeze_match.json#summary.146.all_ofac_chain_addresses.value = 6 -->

**2 addresses** were first frozen before their entire listing day began.
<!-- check: results/freeze_match.json#summary.146.definitely_before_publication.value = 2 -->

The early-frozen pair held **344,211,454.458506 USDT** at first freeze.
<!-- check: results/freeze_match.json#findings.11.metric.value = 344211454.458506 -->

Native USDT units are summed at each address’s first freeze, across different dates; this is not a USD valuation or a simultaneous balance. The remaining freezes occurred on listing day, whose intraday publication time is unknown. The program-level result used here was checked against the ledger and derived rows: its Tron IRAN cohort is exactly the bank’s listed-address set.

Produced by: `scripts/analysis/freeze_match.py` → `results/freeze_match.json#summary.146`; detail: `data/derived/freeze_match.csv`. Independent amount reconstruction: `docs/verify/FREEZE_VERIFY.md` and `data/verify/freeze_verify.csv`.

- [ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe](https://tronscan.org/#/transaction/ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe) — pre-listing-day first freeze at a bank-listed identifier; raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`.
- [295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a](https://tronscan.org/#/transaction/295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a) — the other pre-listing-day first freeze at a bank-listed identifier; raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`.
- [005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4](https://tronscan.org/#/transaction/005818cbe2e237d7ba8fc845d6a1d50db21e3eabc42f6b376c37223902afe8a4) — listing-day first freeze at another bank-listed identifier; raw `data/raw/freezes/tron_events/fd56e4a7a23d7cfb25cb9a7d2304b50f82a9e354430069c70cdacab74d10b1ad.json.gz`.

Prior art: **Confirms and extends.** Tether already announced the early pair’s freeze. This adds the full listed Tron cohort, its native first-freeze subtotal and the distinction between pre-day and same-day events; it does not claim that the freeze itself was undisclosed.

Confidence: **High** for OFAC membership and event ordering; **Medium** for historical balances. The independent verifier reproduces these amounts, while Tron’s non-atomic current observations and incomplete independent pagination checks remain reconstruction limits.

## Tether blacklisted all 341 OFAC-listed Tron addresses.
<!-- check: results/freeze_match.json#summary.112.blacklisted_ever.value = 341 -->

Denominator: **341 historically listed Tron chain-address pairs**, including empty addresses and earlier blacklist events.
<!-- check: results/freeze_match.json#summary.112.all_ofac_chain_addresses.value = 341 -->

**96 addresses** were first blacklisted before the entire OFAC listing day began.
<!-- check: results/freeze_match.json#summary.112.definitely_before_publication.value = 96 -->

Median signed lag from the noon-ET listing-date proxy: **-7.31 hours**.
<!-- check: results/freeze_match.json#summary.112.median_lag_hours.value = -7.3125 -->

Earliest-bound median: **-19.31 hours**, allowing publication anywhere during the listing date.
<!-- check: results/freeze_match.json#summary.112.median_lag_interval_lower_hours.value = -19.31222222222222 -->

Latest-bound median: **+4.69 hours**, under the same publication-time uncertainty.
<!-- check: results/freeze_match.json#summary.112.median_lag_interval_upper_hours.value = 4.6875 -->

The independent audit establishes **at least 529,064,435.426376 USDT** at first freeze, a known-balance lower bound rather than an all-address total.
<!-- audit-check: data/verify/freeze_verify.csv#known_subtotal_native = 529064435.426376 -->

Its known-balance numerator is **334 addresses**, preserving the verifier’s original frozen cohort.
<!-- audit-check: data/verify/freeze_verify.csv#known_addresses = 334 -->

That audit’s inventory denominator is **341 Tron addresses**.
<!-- audit-check: data/verify/freeze_verify.csv#cohort_addresses = 341 -->

First-freeze balances remained unknown for **7 addresses** in that audit cohort; their partial histories are excluded from its subtotal.
<!-- audit-check: data/verify/freeze_verify.csv#unknown_addresses = 7 -->

The audit figures are produced by `scripts/verify/freeze_verify.py`, saved in `data/verify/freeze_verify.csv` and documented in `docs/verify/FREEZE_VERIFY.md`. The explicit audit-check tags preserve that source, because the rebuilt JSON holds a later expanded reconstruction rather than the original verification cohort. The owned checker reproduces the audit subtotal and cohort counts directly from the saved CSV. Native USDT units refer to each first-freeze event, across different dates; they are not USD or one simultaneous balance.

The median does not establish that Tether typically acted before publication: its uncertainty spans either ordering. A blacklist is a restriction on the issuer’s token, not native TRX or proof of a positive token balance. The audit confirms historical membership and current blacklist status.

Produced by: `scripts/analysis/freeze_match.py` → `results/freeze_match.json`; detail: `data/derived/freeze_match.csv`.

- [344407805efd031c4bd1194969da21fe6ec655d93dad2ca66ef3ccede473765b](https://tronscan.org/#/transaction/344407805efd031c4bd1194969da21fe6ec655d93dad2ca66ef3ccede473765b) — earlier blacklist for an identifier OFAC later listed under AL-JEBOURI, Zaid Issam Ahmed; raw `data/raw/freezes/tron_events/8500c77166a42f01eccc2f68d18df4c2dc188c5889b26c0b80e8c6a9e8c59ad4.json.gz`.
- [ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe](https://tronscan.org/#/transaction/ebe670f1518f67077d28ec4b54dd0d236a5f1edfa90651524aeb42a21e6975fe) — pre-listing freeze for BANK MARKAZI JOMHOURI ISLAMI IRAN; raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`.
- [295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a](https://tronscan.org/#/transaction/295cd606150289dc18d9e0e4d9503adb9d1b10bde9c314158f9cfa7c9928b09a) — another pre-listing freeze in the same OFAC-named cohort; raw `data/raw/freezes/tron_events/c5d9d8b2ae122c66bbe889d2128bc5d5fb064efcfc26e177911eb59ec730a23e.json.gz`.

Prior art: **Confirms and extends.** Chainalysis and PublicAML already reported Tron freezes in selected actions; Bitquery already studied issuer timing. This is an exact-identifier historical denominator with signed lag and date uncertainty, not the discovery of Tron enforcement.

Confidence: **High** for blacklist-event membership and pre-day ordering, independently checked. **Medium** for interpreting the proxy median as response speed; earlier freezes can have unrelated causes.

## 497 listed addresses had already sent funds out and held no measured balance when OFAC listed them.
<!-- check: results/checkpoints.json#findings.3.number.value = 497 -->

Denominator with a usable designation checkpoint: **1,002 trackable non-Tornado chain-address pairs**.
<!-- check: results/checkpoints.json#headline_population.addresses_with_T_balance.value = 1002 -->

The broader eligible trackable non-Tornado population contains **1,043 chain-address pairs**; unavailable designation balances are excluded from the measured denominator.
<!-- check: results/checkpoints.json#headline_population.addresses.value = 1043 -->

Each counted address had an earlier qualifying outflow and a reconciled zero balance in recognized assets at the start of its first listing day. This supports “many identifiers were empty before listing”; it does not show that the owner had no other assets or anticipated OFAC.

Produced by: `scripts/analysis/checkpoints.py` → `results/checkpoints.json`; detail: `data/derived/address_summary.csv`.

- [a68bd5004d9c0ed77b9623c5ba58e3e79194b88f3ac191175db88f58908c1056](https://mempool.space/tx/a68bd5004d9c0ed77b9623c5ba58e3e79194b88f3ac191175db88f58908c1056) — earlier BTC outflow from a subsequently empty identifier listed under CHEN, Zhi; raw `data/raw/utxo/btc1.trezor.io/98/980f8089a43f3b15b01960c7f79caa82137d9dd536be3586fbc9c32db0dbb6ac-6b0bf39dbe61b0cc.json.gz#response.transactions[0]`.
- [3dbf21395abddf175bafc55fbeae3d3e958ec9fd1e207c18241916ee1de4da97](https://mempool.space/tx/3dbf21395abddf175bafc55fbeae3d3e958ec9fd1e207c18241916ee1de4da97) — earlier BTC outflow from a subsequently empty identifier listed under CHEN, Zhi; raw `data/raw/utxo/mempool.space/23/235acb009a3cee46734f8716f322e530d8fa86a737f630c695c2b8457328ca89-bb8cafd59adb947c.json.gz#response[0]`.
- [ab7413e5bb8c474146005d1733df3a8da90c7b1a04ef8d50247554648f4764c1](https://mempool.space/tx/ab7413e5bb8c474146005d1733df3a8da90c7b1a04ef8d50247554648f4764c1) — earlier BTC outflow from a subsequently empty identifier listed under CHEN, Zhi; raw `data/raw/utxo/btc1.trezor.io/b5/b5e0e4105ac1ed6f0f10838465b09af4acf2549f1f942bd72e4ee68d19ec023b-3f7b7b15d99e3c87.json.gz#response.transactions[2]`.

Prior art: **New measurement within the reviewed sources.** Earlier papers study post-listing balances or activity; this cross-chain, reconciled empty-at-listing cohort adds the earlier-outflow condition. It is not evidence that an entire named entity was empty.

Confidence: **Medium.** The recognized-asset and reconciliation rules are explicit; unknown assets and incomplete histories remain outside the claim. The examples are concentrated in the CHEN, Zhi cohort, rather than a representative sample.

## Tornado Cash’s ETH deposits rose 154.70% after OFAC removed its designation.
<!-- check: results/tornado.json#findings.0.number.value = 1.547023946937236 -->

Before-window denominator: **17,760.1 ETH deposited** in the classic native-ETH pools.
<!-- check: results/tornado.json#findings.0.before.value = 17760.1 -->

After-window volume: **45,235.4 ETH deposited** in the same pools.
<!-- check: results/tornado.json#findings.0.after.value = 45235.4 -->

Distinct observed transaction origins before: **263 addresses**, not people.
<!-- check: results/tornado.json#findings.0.unique_tx_origins_before.value = 263 -->

Distinct observed transaction origins after: **540 addresses**, not people.
<!-- check: results/tornado.json#findings.0.unique_tx_origins_after.value = 540 -->

Equal calendar windows exclude the delisting day; their exact UTC endpoints are in `results/tornado.json#legal_events.3.before_30d` and `after_30d`. Deposits are native principal, excluding token pools and unrelated transfers. This is an association around a legal event, not an isolated causal effect.

UTC windows, start inclusive and end exclusive: before 2025-02-19 to 2025-03-21; after 2025-03-22 to 2025-04-21.

Produced by: `scripts/analysis/tornado.py` → `results/tornado.json`; detail: `data/derived/tornado_daily.csv`.

- [0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec](https://etherscan.io/tx/0x8d44f26adc506fd1a05bc84be459c79b2fdaf82a3935d65ad5c8a7b7fb8aaeec) — Deposit event in the post-delisting comparison window; raw `data/raw/evm/rpc/768a90a0e23a5b4cd0bfbe4b.json.gz#/response/result/1370`.
- [0xf90c405ae2b8fb2cde2b46da5a5a01c5ad2ddb46b5cecaed4f9d03a41537b9bf](https://etherscan.io/tx/0xf90c405ae2b8fb2cde2b46da5a5a01c5ad2ddb46b5cecaed4f9d03a41537b9bf) — Deposit event in the post-delisting comparison window; raw `data/raw/evm/rpc/6e2e217738416be11ab3ca36.json.gz#/response/result/3249`.
- [0x5d93a2e859d897eefa3ecf94fe24d285f289077eb5b734f16ae67a17ae2c7662](https://etherscan.io/tx/0x5d93a2e859d897eefa3ecf94fe24d285f289077eb5b734f16ae67a17ae2c7662) — Deposit event in the post-delisting comparison window; raw `data/raw/evm/rpc/89dd4c4962c92eb868d0fd94.json.gz#/response/result/3310`.

Prior art: **Confirms and extends.** TRM already discusses use after delisting, and the New York Fed studies reactions to legal developments. The increment is this reproducible equal-window ETH and origin-address comparison.

Confidence: **High** for pool-event counts and ETH principal in these windows. **Medium** for generalizing beyond this protocol/window; market conditions and simultaneous news can explain part of the change.

## The largest post-listing outflows coincide with a DOJ forfeiture and government custody.

Addresses OFAC lists under **CHEN, Zhi sent 1,722,913,707.06 USD** after their identifiers were listed; `valued_at`: each constituent transfer time.
<!-- check: results/flows.json#findings.2.amount.value = 1722913707.055637 -->

Denominator: **2,489,419,653.78 USD** of measured gross wallet outflow value; `valued_at`: each constituent transfer time, across different dates.
<!-- check: results/flows.json#summary.wallet_outflows_usd.value = 2489419653.782674 -->

The CHEN, Zhi result contains **4 outgoing Bitcoin output edges**; edges are not a count of people or unique funds.
<!-- check: results/flows.json#findings.2.events.value = 4 -->

The cited public report describes a DOJ forfeiture and government custody alongside the listing. The largest post-listing transfers came from this cohort. The cited public sources do not name the recipients of these transfers. The chain shows the transfers, but does not establish who controlled those recipients or why each transfer occurred. These outflows cannot be presented as evidence of successful sanctions evasion. Gross output value is not unique wealth.

Produced by: `scripts/analysis/flows.py` → `results/flows.json`; detail: `data/derived/flows_edges.csv`.

- [c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24](https://mempool.space/tx/c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24) — post-listing BTC output edge from a CHEN, Zhi-listed identifier; recipient control is unknown; raw `data/raw/utxo/btc1.trezor.io/0a/0ad65fa1eecd9b209198c537739f4f12fe9e3841bd672431f8e48462a93278d1-d431f26e91059872.json.gz#response.transactions[0]`.
- [b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885](https://mempool.space/tx/b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885) — post-listing BTC output edge from a CHEN, Zhi-listed identifier; recipient control is unknown; raw `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[0]`.
- [e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d](https://mempool.space/tx/e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d) — post-listing BTC output edge from a CHEN, Zhi-listed identifier; recipient control is unknown; raw `data/raw/utxo/btc1.trezor.io/ad/ad5196fbd51b3e7b5f6e8ef2ae314eae2fde8fd1c61273837db96e3f1ee6c77f-a9cff8ff8e5389c8.json.gz#response.transactions[0]`.

Context source: [TRM’s report of the action](https://www.trmlabs.com/resources/blog/historic-u-s--u-k-operation-targets-southeast-asias-scam-compounds-with-record-15-billion-bitcoin-seizure); saved `data/raw/priorart/pages/trm-prince.txt.gz`. The exact source URL is preserved with the result’s `context_sources`.

Prior art: **Confirms context; new cohort decomposition.** The forfeiture was already public. This analysis shows why a large cross-chain “outflow after sanctions” total cannot be equated with successful evasion.

Confidence: **Medium.** The source-address membership and output amounts have raw evidence; custody and purpose of the specific spends remain unresolved. Coverage and public recipient labels are incomplete.

## Addresses moved funds less often in the week before listing than in their own baseline weeks.

Observed pre-week activity: **5.52% of eligible addresses** had a qualifying outflow.
<!-- check: results/premove.json#candidate_findings.0.observed_share.value = 0.0552423900789177 -->

Own-baseline weekly activity averaged **15.35%**, weighting each eligible address equally for this descriptive share.
<!-- check: results/premove.json#candidate_findings.0.baseline_share.value = 0.15349734844775315 -->

Observed numerator: **49 active addresses** in the pre-listing window.
<!-- check: results/premove.json#candidate_findings.0.number.value = 49 -->

Denominator: **887 eligible non-Tornado chain-address pairs** with complete histories and sufficient earlier baseline windows.
<!-- check: results/premove.json#candidate_findings.0.denominator.value = 887 -->

The registered cluster-based test’s Holm-adjusted one-sided **p = 1.0** for excess activity.
<!-- check: results/premove.json#candidate_findings.0.p_holm = 1.0 -->

In the broader checkpoint inventory, **96 addresses** had a qualifying outflow during the pre-listing week; this includes Tornado-associated identifiers.
<!-- check: results/checkpoints.json#aggregates.overall.0.moved_before_addresses.value = 96 -->

The inventory denominator is **1,134 trackable chain-address pairs**; this is not the baseline-test eligibility denominator.
<!-- check: results/checkpoints.json#aggregates.overall.0.addresses.value = 1134 -->

Excluding the Tornado-associated cohort leaves **81 addresses** with pre-week movement.
<!-- check: results/checkpoints.json#headline_population.moved_before_addresses.value = 81 -->

That non-Tornado inventory contains **1,043 trackable chain-address pairs**.
<!-- check: results/checkpoints.json#headline_population.addresses.value = 1043 -->

These checkpoint movement flags and the earlier Tron blacklist count describe different events and different address sets. The eligible own-baseline test is a stricter subset of the non-Tornado inventory. The site’s `first_outflow_days` measures an outgoing transfer selected after the start of listing day; it is not the lag to an earlier pre-listing outflow. An earlier-movement flag therefore does not require a negative first-post-listing lag. The set comparison and export/source checks are recorded in `docs/analysis/FINDINGS_NOTES.md`.

The design excludes the listing day because its publication time is unknown. Matched earlier windows, placebo dates, inactive-address handling and the exchange-scale sensitivity are in the producer’s report. Selected examples show that individual pre-listing transfers occurred; they do not establish a cohort-wide surge.

Produced by: `scripts/analysis/premove.py` → `results/premove.json`; detail: `docs/analysis/PREMOVE.md`.

- [280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53](https://mempool.space/tx/280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53) — observed pre-listing outflow used as an illustrative case, not proof of advance notice; raw `data/raw/utxo/btc1.trezor.io/2f/2f75728ccb6c1932ce21fa57d5832a350b1c351d46a040893d5bdc2b0a317acb-fa713d0510841727.json.gz#response.transactions[78]`.
- [e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b](https://tronscan.org/#/transaction/e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b) — observed pre-listing outflow used as an illustrative case, not proof of advance notice; raw `data/raw/tron/trc20/2c30dd9f719931271b4cd26fc98490482e95ef0e72863a5d9c8c5cb8eb0d6134.json.gz#/response/data/41`.
- [c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73](https://tronscan.org/#/transaction/c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73) — observed pre-listing outflow used as an illustrative case, not proof of advance notice; raw `data/raw/tron/trc20/9a35ecf99419525c870fcfc081eef8353f1bfeb4116056cff4d07100a14f378f.json.gz#/response/data/25`.

Prior art: **New design within the reviewed sources; consistent with earlier anticipation research.** The New York Fed already considers anticipation. The increment is the explicit within-address baseline across this eligible cross-chain population.

Confidence: **Medium.** The registered test does not establish an excess; it cannot prove that no individual received advance notice. Time trends, seizures, nonexchangeable weeks and source gaps limit interpretation.

## Measured designation-date balances shrank by 6.40% within a week.
<!-- check: results/checkpoints.json#headline_population.depletion.T+7d.share.value = 0.06404405982683141 -->

Net-depleted numerator: **264,133,333.05 USD**; `valued_at`: each address’s own designation-date prices, held fixed for the comparison.
<!-- check: results/checkpoints.json#headline_population.depletion.T+7d.net_depleted_T_value.value = 264133333.0538568 -->

Value denominator: **4,124,244,055.86 USD**; `valued_at`: each address’s own designation-date prices, across mixed historical dates.
<!-- check: results/checkpoints.json#headline_population.depletion.T+7d.T_value_denominator.value = 4124244055.858519 -->

Measured denominator: **491 non-Tornado chain-address pairs** with positive, reconciled eligible value and both checkpoints.
<!-- check: results/checkpoints.json#headline_population.depletion.T+7d.addresses.value = 491 -->

CHEN, Zhi-listed identifiers account for **63.38% of that designation-value denominator**.
<!-- check: results/checkpoints.json#concentration_sensitivity.0.share_of_7d_value_denominator.value = 0.6338337013730101 -->

Excluding that cohort changes the net-depletion share to **17.49%**.
<!-- check: results/checkpoints.json#concentration_sensitivity.0.excluding_this_entity.depletion.T+7d.share.value = 0.17490429913123293 -->

The exclusion’s value denominator is **1,510,159,180.57 USD**; `valued_at`: each remaining address’s own designation-date prices.
<!-- check: results/checkpoints.json#concentration_sensitivity.0.excluding_this_entity.depletion.T+7d.T_value_denominator.value = 1510159180.5680785 -->

The exclusion’s measured address denominator is **481 chain-address pairs**.
<!-- check: results/checkpoints.json#concentration_sensitivity.0.excluding_this_entity.depletion.T+7d.addresses.value = 481 -->

This is the sum of per-asset positive balance decreases, valued at designation prices. Replenishment can hide withdrawals, and the calculation does not identify which original units moved. Retained value may be frozen or under government custody. “Only this much left” would overstate what the statistic measures.

Produced by: `scripts/analysis/checkpoints.py` → `results/checkpoints.json`; detail: `data/derived/address_summary.csv`.

- [0x6240848d80e7de9ac42fa16dd121f702bdf94183f05cda310adcb7a135ff9336](https://etherscan.io/tx/0x6240848d80e7de9ac42fa16dd121f702bdf94183f05cda310adcb7a135ff9336) — observed early post-listing outflow from a LAZARUS GROUP-listed address; balance depletion is reconstructed separately; raw `data/raw/evm/etherscan/f53be75d9098b9a5223f883c.json.gz#/response/result/354`.
- [0x7af5e2ce1d8f88c3a824d1569da4fc828965bb0a603e7951e739bf1764ba5374](https://etherscan.io/tx/0x7af5e2ce1d8f88c3a824d1569da4fc828965bb0a603e7951e739bf1764ba5374) — observed early post-listing outflow from a LAZARUS GROUP-listed address; balance depletion is reconstructed separately; raw `data/raw/evm/etherscan/52c7f709b632ddf175fcdc0a.json.gz#/response/result/5`.
- [0x8c92d82248ad2f0b1437b375f7b7e8e7777b41023a58dabb8c2ad1f7a6e26f62](https://etherscan.io/tx/0x8c92d82248ad2f0b1437b375f7b7e8e7777b41023a58dabb8c2ad1f7a6e26f62) — observed early post-listing outflow from a LAZARUS GROUP-listed address; balance depletion is reconstructed separately; raw `data/raw/evm/etherscan/ee2de15850ee3f174e0c87e4.json.gz#/response/result/4`.

Prior art: **New measured cross-chain checkpoint comparison; confirms the need for cohort distinctions.** Ethereum and Bitcoin papers already study post-listing changes. Their endpoint/cohort results are not a direct benchmark for this week-long recognized-asset depletion measure.

Confidence: **Medium.** The measured subset reconciles, but concentration materially changes the estimate, incomplete assets are excluded, and this is not a population-wide gross escape rate.

## Tornado Cash makes Tether’s Ethereum freeze lag look far slower than its wallet-only lag.

Circle’s full-cohort median signed lag is **8.31 hours** from the noon-ET listing-date proxy.
<!-- check: results/freeze_match.json#summary.0.median_lag_hours.value = 8.309722222222224 -->

Tether’s full-cohort median on Ethereum is **9,504.06 hours** under the same proxy.
<!-- check: results/freeze_match.json#summary.56.median_lag_hours.value = 9504.058055555555 -->

Each full-cohort median uses **216 ever-blacklisted valid Ethereum identifiers**.
<!-- check: results/freeze_match.json#summary.56.blacklisted_ever.value = 216 -->

The historical listing denominator is **217 Ethereum strings**, including an invalid identifier that cannot be ABI-encoded as an address.
<!-- check: results/freeze_match.json#summary.56.all_ofac_chain_addresses.value = 217 -->

Excluding the Tornado-associated cohort, Tether’s median is **6.27 hours**.
<!-- check: results/freeze_match.json#summary.57.median_lag_hours.value = 6.266388888888889 -->

Circle’s corresponding non-Tornado median is **3.44 hours**.
<!-- check: results/freeze_match.json#summary.1.median_lag_hours.value = 3.4363888888888887 -->

Each non-Tornado median uses **125 ever-blacklisted identifiers**.
<!-- check: results/freeze_match.json#summary.57.blacklisted_ever.value = 125 -->

The large full-cohort delay reflects the retrospective Tether policy batch and cohort composition, not a comparable current response-time experiment. Intraday OFAC timing is unknown; same-day issuer ordering should be read from matched on-chain events rather than inferred from the publication proxy.

Produced by: `scripts/analysis/freeze_match.py` → `results/freeze_match.json`; detail: `data/derived/freeze_match.csv`.

- [0x3c0978677bac14d4dd33b1b3ed4badfd4e03416fce640e23b273366f60945fc4](https://etherscan.io/tx/0x3c0978677bac14d4dd33b1b3ed4badfd4e03416fce640e23b273366f60945fc4) — Tether’s retrospective blacklist batch affecting an earlier Tornado identifier; raw `data/raw/freezes/logs/0fbe6c7324bfb44c48358c58802ca608dbc1346054eb55b67cb806c702177884.json.gz`.
- [0xb993aa7b35cd6278b10bec5ab86a9b1fbaa5f0e6b68e6843dd57d09fde963ea4](https://etherscan.io/tx/0xb993aa7b35cd6278b10bec5ab86a9b1fbaa5f0e6b68e6843dd57d09fde963ea4) — Tether’s retrospective blacklist batch affecting an earlier Tornado identifier; raw `data/raw/freezes/logs/0fbe6c7324bfb44c48358c58802ca608dbc1346054eb55b67cb806c702177884.json.gz`.
- [0x5906c3dac2d75f141b72baa61842a9881e9d31ee36f761ffc7059ffc86c7e452](https://etherscan.io/tx/0x5906c3dac2d75f141b72baa61842a9881e9d31ee36f761ffc7059ffc86c7e452) — Circle event from a matched identifier action; context for comparing issuer histories; raw `data/raw/freezes/logs/d221629fdcfabd20b31627d3ffb24d92f23e1ee8da99492e0cddd93b67b5480b.json.gz`.

Prior art: **Confirms and refines.** Liu’s current Ethereum paper and Bitquery already compare issuer delays. Separating Tornado and policy-era cohorts prevents a misleading blanket ranking; issuer-lag analysis itself is not new.

Confidence: **High** for event timestamps and cohort arithmetic, with Circle’s full-cohort result independently verified. **Medium** as an enforcement-speed comparison because policy eras, contracts, holdings and listing-date precision differ.

## The biggest observed qualifying receipt moved between addresses listed under the same OFAC name.

Largest receipt at a SEMENOV, Roman-listed address: **1,341,519.11 USD**; `valued_at`: 2023-11-27T02:00:00Z, the saved price observation for that transfer.
<!-- check: results/inflows.json#headline_candidates.0.largest_inflow_usd.value = 1341519.11 -->

That recipient’s observed qualifying subtotal is **1,341,680.82 USD**; `valued_at`: each constituent transfer’s historical price observation.
<!-- check: results/inflows.json#headline_candidates.0.real_inflow_usd.value = 1341680.82 -->

Its recipient-level denominator is **2 qualifying incoming transfer events**.
<!-- check: results/inflows.json#headline_candidates.0.real_events.value = 2 -->

Across the wallet study, removing senders sharing the recipient’s OFAC UID leaves **1,563,645.74 USD**; `valued_at`: each retained transfer’s historical price observation.
<!-- check: results/inflows.json#wallet_excluding_senders_sharing_recipient_ofac_uid.real_inflow_usd.value = 1563645.74 -->

The comparison denominator is **2,905,356.06 USD** before that same-UID exclusion; `valued_at`: each qualifying transfer’s historical price observation.
<!-- check: results/inflows.json#wallet_during_sanctions.real_inflow_usd.value = 2905356.06 -->

Both endpoints of the largest receipt share an OFAC UID. That is evidence of an internal listed-entity link, not new customer demand or proof of current common control. The smaller receipt is from an unlabelled sender; excluding known same-UID senders does not establish that everything remaining is external funding.

Produced by: `scripts/analysis/inflows.py` → `results/inflows.json`; detail: `data/derived/inflows.csv`.

- [0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73](https://etherscan.io/tx/0x348084aeeec7654a6f54651bc44af009fad658f5ea794b75010b75a0e6bcaa73) — the largest receipt, whose sender shares the recipient’s OFAC UID; raw `data/raw/evm/etherscan/e50db83fbf6fcb8b69607a0b.json.gz#/response/result/49`.
- [0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32](https://etherscan.io/tx/0xc55a5a7c1879eb548911b5bb45f985ee9dc802768901560acc194eee3b62bd32) — the same recipient’s other qualifying receipt, from an unlabelled sender; contextual comparison; raw `data/raw/evm/etherscan/3d9dd1d54e3a3425194382f8.json.gz#/response/result/60`.

Prior art: **New accounting detail within the reviewed sources; consistent with prior cautions.** PublicAML already separates internal flows in case work. Here the exact UID-linked receipt explains why gross inflows overstate demonstrated outside payments.

Confidence: **High** for the saved transfer and shared OFAC UID; **Medium** for the broader subtotal because sender labels and token/history coverage are incomplete. No controller identity is inferred.

## Only 329 incoming transfers passed the study’s value and token filters during listing periods.
<!-- check: results/inflows.json#wallet_during_sanctions.real_events.value = 329 -->

These records sum to **2,905,356.06 USD**; `valued_at`: each transfer’s saved historical price observation, with exact times and price sources in the derived transfer table.
<!-- check: results/inflows.json#wallet_during_sanctions.real_inflow_usd.value = 2905356.06 -->

Receiving numerator: **103 non-Tornado chain-address pairs**.
<!-- check: results/inflows.json#wallet_during_sanctions.receiving_addresses.value = 103 -->

Observed incoming-record denominator: **28,244 transfer records** during listing periods, including dust, operational spam and unpriced records.
<!-- check: results/inflows.json#wallet_during_sanctions.inflow_events.value = 28244 -->

The counted qualifying transfers represent **319 distinct transaction hashes**.
<!-- check: results/inflows.json#wallet_during_sanctions.distinct_transactions.value = 319 -->

Dropping the entire intraday-ambiguous listing date leaves **1,889,322.96 USD**; `valued_at`: each retained transfer’s historical price observation.
<!-- check: results/inflows.json#wallet_during_sanctions.real_usd_after_designation_day.value = 1889322.96 -->

Exceptions include repeated receipts at CHATEX-listed identifiers, small recurring receipts at AL-LAW, Tawfiq Muhammad Sa’id’s listed Tron address, and much later receipts at SECONDEYE SOLUTION. Public labels and sender patterns do not establish donations, victim payments, payroll, or the number of people. UTXO net credits can include consolidation; this is a filtered observed subtotal, not all incoming wealth.

Produced by: `scripts/analysis/inflows.py` → `results/inflows.json`; detail: `data/derived/inflows.csv`.

- [0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000](https://etherscan.io/tx/0xd81e6d7818a10b2704b65ddd6ec270b23fa464d0aa8787ad723f79326d23d000) — qualifying receipt at a CHATEX-listed address; raw `data/raw/evm/etherscan/261226a12b77f3a7ba615e4e.json.gz#/response/result/76`.
- [faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06](https://tronscan.org/#/transaction/faa486b01a9ed34bad2c3505aa6159eba7aa36b05ff79e8163684ad3bbdbbe06) — qualifying receipt at AL-LAW, Tawfiq Muhammad Sa’id’s listed address; raw `data/raw/tron/native/d417c27b9007ecf1e0b758674bef24089d1bcf885e09f1bee07b47c9ed0695cd.json.gz#/response/data/164`.
- [0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f](https://etherscan.io/tx/0x37676e6b94021f4f64dc7a57d6c2e8503fa7d170b3dcd051f0f7060ac03bef4f) — qualifying late receipt at a SECONDEYE SOLUTION-listed address; raw `data/raw/evm/etherscan/f4c62957d25cb844679c5b0e.json.gz#/response/result/71`.

Prior art: **New scoped measurement; confirms prior warnings about incoming-record counts.** Liu already studies dust/poisoning and PublicAML distinguishes substantive payments from small residual activity. The increment is this explicit classification at listed identifiers across covered chains.

Confidence: **Medium.** Amounts and examples have raw evidence, but thresholds, token recognition, incomplete histories and ambiguous listing-day order affect the observed subtotal. “Qualifying” is not a determination of economic purpose.

## Tornado Cash’s classic ETH pools now hold more ETH than at the paper’s delisting-period endpoint.

Latest common saved pool balance: **309,794.3 ETH**, observed_at: 2026-10-22T21:58:11Z.
<!-- check: results/tornado.json#findings.2.number.value = 309794.3 -->

Comparison denominator: **144,294.8 ETH** at the prior paper’s explicit endpoint block; this is the same pool cohort, not the paper’s entire address population.
<!-- check: results/tornado.json#findings.2.at_paper_endpoint.value = 144294.8 -->

Balance growth between those observations: **114.70%**.
<!-- check: results/tornado.json#findings.2.growth_share.value = 1.1469540135888474 -->

These are independent native-balance observations. The accompanying transaction links illustrate later deposits; they do not by themselves prove the aggregate stock. Current observations are after delisting, and cannot be presented as activity while the designation remained in force. This uses the common observation in the dedicated Tornado result, rather than mixing later per-pool observations from the cases result.

Produced by: `scripts/analysis/tornado.py` → `results/tornado.json`; detail: `data/derived/tornado_daily.csv`.

- [0x650311f3a8854bdd5ddbead3720d26d6cc9146fc71cbe7c8c271b2c0a8523b3a](https://etherscan.io/tx/0x650311f3a8854bdd5ddbead3720d26d6cc9146fc71cbe7c8c271b2c0a8523b3a) — later Deposit event illustrating continuing pool use; state-query refs establish the balance; raw `data/raw/evm/rpc/55146e0675bf985bdfc508cc.json.gz#/response/result/7860`.
- [0x38c7d6896950a89ae0336991ea065f8dffb238e8edd062c4fe745b13310b50d3](https://etherscan.io/tx/0x38c7d6896950a89ae0336991ea065f8dffb238e8edd062c4fe745b13310b50d3) — later Deposit event illustrating continuing pool use; state-query refs establish the balance; raw `data/raw/evm/rpc/97a6dd75a814d4f37e421dc0.json.gz#/response/result/4667`.
- [0x956dfbfd35c79aadcf7f57c376fdc2a6461aa09e87b77b93ed7c9b11a5e63532](https://etherscan.io/tx/0x956dfbfd35c79aadcf7f57c376fdc2a6461aa09e87b77b93ed7c9b11a5e63532) — later Deposit event illustrating continuing pool use; state-query refs establish the balance; raw `data/raw/evm/rpc/ebe5aeb76746f965031aec65.json.gz#/response/result/8083`.

Balance raw evidence: `results/tornado.json#findings.2.raw_refs` and `legal_checkpoint_balances` preserve the exact RPC requests and blocks.

Prior art: **Extends.** The Ethereum paper already reports remaining holdings, the New York Fed distinguishes balances from activity, and TRM discusses post-delisting use. This adds a later, explicitly dated same-pool stock comparison.

Confidence: **High** for the stated direct native-balance observations. Balances do not identify users, unique source funds, current ownership or legal compliance; later saved observations can differ.

## Tornado Cash’s native-ETH deposit change around its initial designation was −67.96%.
<!-- check: results/tornado.json#findings.4.number.value = -0.6795872162179912 -->

Before-window denominator: **109,626.4 ETH deposited** into the same classic native-ETH pools.
<!-- check: results/tornado.json#findings.4.before.value = 109626.4 -->

After-window volume: **35,125.7 ETH deposited**.
<!-- check: results/tornado.json#findings.4.after.value = 35125.7 -->

These equal calendar windows exclude the designation date; exact boundaries appear in `results/tornado.json#legal_events.0`. The before and after volumes are native principal, not dollars, downstream taint or balances remaining in the pools.

UTC windows, start inclusive and end exclusive: before 2022-07-09 to 2022-08-08; after 2022-08-09 to 2022-09-08.

Produced by: `scripts/analysis/tornado.py` → `results/tornado.json`; detail: `data/derived/tornado_daily.csv`.

- [0x39e477e177999a8f879ef4505c9fa8df1549b24cc5be946959b532f7632ce182](https://etherscan.io/tx/0x39e477e177999a8f879ef4505c9fa8df1549b24cc5be946959b532f7632ce182) — Deposit event in the post-designation comparison window, while the protocol remained usable; raw `data/raw/evm/rpc/3555e075d4a469d7e8863ed9.json.gz#/response/result/7250`.
- [0x3b9f1a2628a2652408ee7f6ee2a6221e712f19bd007e1f32250bf1d87b9253e7](https://etherscan.io/tx/0x3b9f1a2628a2652408ee7f6ee2a6221e712f19bd007e1f32250bf1d87b9253e7) — Deposit event in the post-designation comparison window, while the protocol remained usable; raw `data/raw/evm/rpc/d1f6c7cf92de96a7a4171f35.json.gz#/response/result/2821`.
- [0x780302391733404241d454c518859fad508e09146b52b8e416fedd2c5c8b1a70](https://etherscan.io/tx/0x780302391733404241d454c518859fad508e09146b52b8e416fedd2c5c8b1a70) — Deposit event in the post-designation comparison window, while the protocol remained usable; raw `data/raw/evm/rpc/0532eda0fbbc1ce02c3591d6.json.gz#/response/result/4345`.

Prior art: **Confirms.** Liu, the New York Fed, Chainalysis and TRM already report reduced protocol activity. This equal-window estimate uses a different period from Liu’s longer sanctions-period comparison; it neither replaces nor contradicts that result.

Confidence: **High** for native-principal event arithmetic in these windows; **Medium** for causal interpretation. Usage changes can reflect market conditions, participant substitution and concurrent news.

## 98.83% of incoming records were dust or operational spam under the study’s rules.
<!-- check: results/inflows.json#classification_audit.dust_or_operational_spam_share_of_incoming_records.value = 0.9883161 -->

Denominator: **28,244 observed incoming transfer records** to non-Tornado listed identifiers during listing periods.
<!-- check: results/inflows.json#wallet_during_sanctions.inflow_events.value = 28244 -->

Dust bucket: **26,208 records**, based on the recognized-asset value rules.
<!-- check: results/inflows.json#wallet_during_sanctions.dust_events.value = 26208 -->

Operational spam/poisoning bucket: **1,706 records**, including off-list tokens whose authenticity is unresolved.
<!-- check: results/inflows.json#wallet_during_sanctions.poisoning_events.value = 1706 -->

Only **13 records** met the explicit prior-counterparty address-mimic pattern rule.
<!-- check: results/inflows.json#classification_audit.mimic_pattern_records.value = 13 -->

The combined share is about records, not value, people or independently proven scam attempts. Off-list status is not proof a token is fake, and a small transfer is not evidence of sender intent. A recognized but unpriced token remains unclassified rather than being invented as a dollar amount.

Produced by: `scripts/analysis/inflows.py` → `results/inflows.json`; detail: `data/derived/inflows.csv`.

- [0x0a094420b6ffe21698776a4dc5a2566c6d82ff8efcb9576016b5061ae4a53c60](https://etherscan.io/tx/0x0a094420b6ffe21698776a4dc5a2566c6d82ff8efcb9576016b5061ae4a53c60) — address-mimic rule match; the pattern does not establish intent; raw `data/raw/evm/etherscan/e89c4bb956b6d333ee51d5a3.json.gz#/response/result/37`.
- [0xd33ef30ec1599aa18e14db9de153659d01c336c6e828eaadc559d62d8c793480](https://etherscan.io/tx/0xd33ef30ec1599aa18e14db9de153659d01c336c6e828eaadc559d62d8c793480) — address-mimic rule match; the pattern does not establish intent; raw `data/raw/evm/etherscan/3d9dd1d54e3a3425194382f8.json.gz#/response/result/63`.
- [0x1b25e6ad8a3344a18a23cffeda2759e8e7d7848115d7196045a5cff0ad2c77fa](https://etherscan.io/tx/0x1b25e6ad8a3344a18a23cffeda2759e8e7d7848115d7196045a5cff0ad2c77fa) — address-mimic rule match; the pattern does not establish intent; raw `data/raw/evm/etherscan/f53be75d9098b9a5223f883c.json.gz#/response/result/429`.

Prior art: **Confirms and extends.** Liu explicitly covers dust and address poisoning; PublicAML already separates tiny residual transfers. The addition is a reproducible record-level audit for the covered listed-address cohort, with unresolved authenticity preserved.

Confidence: **High** for recorded zero/small amounts and deterministic rule counts. **Medium** for the combined operational classification, which can include legitimate off-list assets and does not determine economic purpose.

## Public service labels leave 99.85% of measured first-hop outflow value unclassified.
<!-- check: results/flows.json#findings.3.amount.value = 0.998514 -->

Unlabelled-role numerator: **2,485,721,599.48 USD**; `valued_at`: each first-hop transfer’s historical price observation.
<!-- check: results/flows.json#summary.classes.8.usd.value = 2485721599.475653 -->

Denominator: **2,489,419,653.78 USD** in priced wallet outflow edges; `valued_at`: each edge’s historical transfer time.
<!-- check: results/flows.json#findings.3.denominator.value = 2489419653.782674 -->

“Unlabelled” means the saved public label set supplies no supported service role at the first destination. It includes a recipient whose ownership is unknown and output attribution the study cannot resolve. A later path may reach a known service; the study’s temporal path heuristic does not allocate the original seed amount to that service. The result is an evidence limit, not a claim that the money disappeared.

Produced by: `scripts/analysis/flows.py` → `results/flows.json`; detail: `data/derived/flows_edges.csv`.

- [c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24](https://mempool.space/tx/c2e8cc3a8feea632837d25ed28856f5b4204cc3f2533f6f8aca17c8e15c67c24) — first-hop BTC recipient lacks a supported service-role label in this snapshot; raw `data/raw/utxo/btc1.trezor.io/0a/0ad65fa1eecd9b209198c537739f4f12fe9e3841bd672431f8e48462a93278d1-d431f26e91059872.json.gz#response.transactions[0]`.
- [b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885](https://mempool.space/tx/b0ac2d705afb1a59e17bbf5a090a5e28cf7f18eaee84eb1ef7dd43ee4fcc6885) — first-hop BTC recipient lacks a supported service-role label in this snapshot; raw `data/raw/utxo/btc1.trezor.io/57/579ca772464c7943683ba261c906a1dac53c670f3c6b46b94c1056f5cd4bcd4f-a5abc97c5dff1e4a.json.gz#response.transactions[0]`.
- [e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d](https://mempool.space/tx/e16a50cedfeaa7bb8e6d95347495c21cfe9201c468e1dbd42f0734c26ba5e24d) — first-hop BTC recipient lacks a supported service-role label in this snapshot; raw `data/raw/utxo/btc1.trezor.io/ad/ad5196fbd51b3e7b5f6e8ef2ae314eae2fde8fd1c61273837db96e3f1ee6c77f-a9cff8ff8e5389c8.json.gz#response.transactions[0]`.

Prior art: **New label-coverage measurement, not new tracing.** The Ethereum and Bitcoin papers already trace service destinations; the Bitcoin paper cautions that labels are incomplete. Their labelled-graph counts and modelled exposures are different denominators from this value share.

Confidence: **High** for the saved dataset’s role-label coverage. **Low** for inferring the actual destination-service distribution: scarce public labels and unresolved UTXO attribution dominate, so a complete “where the money went” account is not supported.

## What we could not see

Coverage is per chain and asset; a timeline file can be a stub. Missing observations are unknown balances or activity, never zero. [COVERAGE](docs/COVERAGE.md) and the producer-specific reports contain the source-level details.

- **Tron:** acquisition has finished, but native TRX can fail reconciliation because of staking, rewards or resources. Some historical first-freeze USDT balances remain unknown. Current-state calls are non-atomic, and a negative noon-proxy lag does not prove freezing preceded publication. The independent audit’s original known-balance cohort is preserved separately from later acquisition updates.
- **Ethereum:** recognized-token and native reconciliation have unresolved gaps; unrelated tokens and administration calls are outside the Tornado principal-event scope. An invalid listed hex string is retained as unqueryable. Issuer coverage here is limited to Ethereum USDT/USDC and Tron USDT.
- **Arbitrum and ETC:** available ordinary histories do not establish universal token, trace or issuer-event coverage. Same-address observations on Polygon and Optimism are separate from the OFAC-listed-chain denominator.
- **BSC and Base:** accessible full historical indexing is incomplete; latest-state evidence is not a complete transfer history.
- **Bitcoin:** saved address histories support the measured debits/credits, but change, co-input funding, recipient ownership and downstream allocation remain uncertain. **BCH, BSV, DASH, DOGE and LTC:** native histories do not establish token-layer or full service-label coverage.
- **Bitcoin Gold:** a later fetcher found a history route while the ledger still marks it untrackable; this inconsistency remains explicit rather than silently changing the population.
- **BNB Beacon:** legacy observations do not establish current spendability or migrated BSC holdings. **XRP:** address history does not eliminate destination-tag and asset-interpretation limitations.
- **Solana:** token-account discovery and full history are incomplete. **Monero:** public identifiers cannot reveal address-level balances or spend linkage without private view keys. **Verge and Zcash:** usable histories were unavailable in the checked sources; shielded Zcash activity cannot be attributed to a transparent identifier.

Across chains, public labels cannot identify most destination services; labelled receipt is neither ownership proof nor evidence of a legal violation. Unknown token prices, off-list assets, unavailable archive states, missing exact OFAC publication times and unequal observation periods limit comparisons. Neither “no outflow found” nor “no excess pre-week activity found” proves universal inactivity or the absence of advance notice.
