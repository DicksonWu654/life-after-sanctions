# Pre-designation movement — pre-registered design

Status: design recorded before inspecting address-level outcomes, 2026-10-23 UTC.
Implementation: `scripts/analysis/premove.py`; results: `results/premove.json`.

## Locked design

1. **Population and clock.** One observation is one listed chain–address pair in `data/addresses.csv`, joined to the ledger's OFAC names, programs, first-publication actions and evidence. Never merge activity on other chains into this population. T is `first_listed_date`, at 00:00 America/New_York (start of the designation day), or an explicitly evidenced exact publication time. Use half-open intervals [T−w days,T), for w=7 (primary), 3 and 1 (secondary). Calendar-day arithmetic in Eastern time handles daylight saving. This excludes announcement-day activity when publication time is unknown; a date does not establish intraday notice.
2. **Eligibility fixed at N=12 baseline weeks.** Require a readable history explicitly marked complete, at least 12 earlier observed weekly windows and a history reaching the event window. Begin exposure at the first confirmed, timestamped transaction, rather than adding fictitious inactive time before first use. Baseline endpoints are T−35, T−42, T−49, ... days, with each window of length w; include every such window starting after first use. This preserves weekday and time of day, avoids overlapping baseline windows, and excludes the entire last 30 days. A three- or one-day sensitivity uses the same weekly sampling grid and N. Incomplete histories are descriptive only; never turn missing history into zero activity. Corrupt/partial files and malformed rows are skipped and counted.
3. **Transfers, assets, prices.** Use successful confirmed outward transfers, excluding fees, self-transfers, zero values and transfers below USD 1 at transfer time. Use the repository price helper offline; trust native assets and an explicit issuer/contract allowlist for tokens, never API symbols alone. Counterfeit/unrecognised tokens are excluded and counted. Unknown prices are missing, never USD 0. Binary activity is within the recognised, price-covered assets. The USD metric requires all recognised positive transfers in the compared windows to have prices; otherwise omit that address from that metric. Sum USD valued at each transfer time, retaining the actual price observation and raw reference. USD totals across windows represent historical transfer-time value, not current wealth.
4. **Balance share.** Reconstruct native-unit starting balances from full-history signed transfers and recorded fees, then value both each window's outgoing native amounts and its starting balance at that window's start. Use all recognised assets with reliable accounting; require nonnegative reconstructed paths and an independently observed compatible end balance, or mark the metric unavailable. Unreconciled/unsupported asset accounting is not a zero balance. Gross outflow divided by opening balance is a turnover ratio and can exceed 1 with in-window replenishment. Zero/unknown denominators are unavailable; do not cap or fabricate a share. Report asset/accounting coverage.
5. **Within-address test.** Compute the midrank percentile of the real window among baseline windows and the real window: (number strictly below + half the ties, including the real window)/(B+1). Also give the conservative one-sided upper-tail empirical p=(1+number baseline >= real)/(B+1). Ties in binary outcomes must remain ties; inactive addresses cannot manufacture significance. Report real outflow, baseline mean/median/max, weekly active fraction and window count, with evidence-linked transactions for extreme cases.
6. **Pooled inference and dependence.** Pool centered address midranks (rank−0.5), first averaging addresses within connected components linking shared first-publication OFAC action OR shared OFAC entity UID. This is more conservative than treating each wallet as independent. Report address-weighted descriptive ranks separately. Under a conditional exchangeability null, permute each address's event label among its baseline+real windows, using one common uniform draw per connected component and inverse empirical rank distributions to preserve positive within-cluster dependence. Average component scores; one-sided Monte Carlo upper-tail test, seed 20261023, 9,999 draws with +1 correction. Also report action-only and entity-only partitions; an entity with multiple actions links them in the primary partition. This is a pooled rank diagnostic, not a causal or calibrated time-series randomization experiment: serial dependence, trends and common shocks violate exchangeability. Report component count, avoid asymptotic significance claims with small component counts.
7. **Placebos and multiplicity.** Repeat the complete procedure for fake T shifted −60, −90 and −180 calendar days, rebuilding eligibility and baseline at each fake date. Report both the available cohorts and a common-address cohort across actual+three fake dates. Placebos are falsification checks, not an assumption they must be null. A significant placebo weakens an anticipation interpretation. Apply Holm adjustment to the primary 7-day pooled tests for three metrics (any outflow, starting-balance turnover, USD); secondary horizons, strata and individual cases are exploratory. Do not select a horizon, N or buffer after viewing results.
8. **Strata and inactive cases.** Separate chain, OFAC program and first-publication action. Program membership can overlap; never sum program totals. Show action/entity clustering. Exclude all Tornado-named entity addresses from wallet-level headline results (conservative pool/router contamination control), retain their coverage counts for the Tornado analysis. Retain exchange-scale addresses (>10,000 distinct confirmed transaction hashes), report with and without. Separate addresses with no recognised non-dust outgoing transfer across real+baseline windows from active histories; report unknown-price ambiguity.
9. **Extreme cases and interpretation.** Rank individual positive-outflow cases first by empirical upper-tail p then descending real transfer-time USD; retain at most 20 primary 7-day cases and up to three distinct example hashes per case, with explorer URLs, raw transaction references, action evidence, OFAC names, baseline and cluster IDs. They are selected exploratorily, not discoveries after a multiple-testing correction. Where available attach saved case/vendor context without inventing publication chronology. Possible explanations include routine treasury operations, market trends, concurrent seizures/indictments, earlier vendor reporting and exchange failures. No result is proof of a leak or unlawful conduct; destination labels are leads, not ownership proof. This is research, not legal advice.
10. **Live-input reproducibility.** Results remain `provisional:true` while fetchers run. Record the timeline inventory and compressed-content hashes used, input hashes, ledger/trackable/missing/unreadable/partial/complete counts, chain exclusions and observation end dates. Save the JSON atomically. `--check` recomputes offline from that saved inventory, checks source hashes first, and exits nonzero on input drift or numerical differences; rerun unchanged to adopt new/updated timelines. An optional in-script synthetic `--self-test` checks boundaries, ties, missing prices, clustering and corrupt-input handling. No network calls or dependency installs. Coverage notes are retained here and in the JSON.

## Implementation and snapshot results

Completed bounded snapshot: 2026-10-23T21:11:42.815615+00:00. `provisional:false`; acquisition is complete for the bounded study; history exceptions remain.

Population: 1,148 listed chain–address pairs; 1,134 trackable, 14 untrackable. 1,147 ledger pairs have timeline files (including coverage stubs and excluded Tornado rows); 0 unreadable/partial files. 91 Tornado-associated pairs are excluded from wallet statistics.

The primary 7-day test has **887 eligible wallet addresses**, of which **214 have no recognised non-dust outflow in any tested real/baseline window**. Inactivity is within the checked assets and time windows, not a statement that the address never transacted.


### Candidate findings to review

The registered primary test does not establish a cohort-wide excess of pre-designation outflow.

**49 addresses of 887 eligible addresses** had pre-week non-dust outflow; observed address share 0.05524, mean own-baseline weekly share 0.1535. 59 connected action/entity clusters; Holm p=1. Common-cohort fake-date binary p values: {'60': 1.0, '90': 0.9962, '180': 1.0}.

Provisional cohort and conditional rank diagnostic; selected examples illustrate observed transfers, not the population estimate. A nonsignificant result does not establish no anticipation. Fake-date tests, time trends, enforcement events and source coverage limit interpretation.

- [280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53](https://mempool.space/tx/280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53) (BTC, 2022-04-04T20:28:58Z); USD 43,585.10 at transfer time; price observation 2022-04-04T20:00:00Z.
- [e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b](https://tronscan.org/#/transaction/e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b) (TRX, 2026-09-03T13:10:48Z); USD 93,600.16 at transfer time; price observation 2026-09-03T13:00:00Z.
- [c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73](https://tronscan.org/#/transaction/c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73) (TRX, 2025-03-30T22:56:03Z); USD 20,045.99 at transfer time; price observation 2025-03-30T22:00:00Z.

HYDRA MARKET had a large outward transfer-time value in the last checked week before its identifier was published.

**USD 1,041,424.21, valued at each transfer time**; own-baseline weekly mean USD 251,674.52, maximum USD 575,590.95; 66 baseline weeks, active fraction 1. Individual upper-tail p=0.01493.

Shorter-window outward USD at transfer times: {'1': 814352.1769166674, '3': 841858.4607536771}. Individual fake-date USD upper-tail p values: {'60': 0.7241379310344828, '90': 0.2222222222222222, '180': 0.04878048780487805}. Small fake-date p values weaken an anticipation interpretation for this case.

Exploratory selection, no individual multiplicity correction. Timestamped transfers and source prices are evidence for movement; neither their size nor their timing establishes a leak, intent, historical recipient control or unlawful conduct.

- [280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53](https://mempool.space/tx/280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53) (BTC, 2022-04-04T20:28:58Z); USD 43,585.10 at transfer time; price observation 2022-04-04T20:00:00Z.
- [ce85dbf04ef58ef3ac4570c15ec1d2403c4276e74f4dba3afc55f60935e86160](https://mempool.space/tx/ce85dbf04ef58ef3ac4570c15ec1d2403c4276e74f4dba3afc55f60935e86160) (BTC, 2022-04-01T15:47:11Z); USD 36,908.57 at transfer time; price observation 2022-04-01T15:00:00Z.
- [c44a4367af181073aecce5afc74dc9d57ec1402c3227afeed8d9062c85635d0e](https://mempool.space/tx/c44a4367af181073aecce5afc74dc9d57ec1402c3227afeed8d9062c85635d0e) (BTC, 2022-03-31T20:56:45Z); USD 33,273.12 at transfer time; price observation 2022-03-31T20:00:00Z.

Saved context: Concurrent seizure is a confounder for a sanctions-only interpretation. [Source](https://ofac.treasury.gov/recent-actions/20220405); `data/raw/priorart/pages/ofac-20220405.html.gz; data/raw/priorart/pages/treasury-hydra-garantex.html.gz; data/raw/priorart/pages/chainalysis-2022-impact.html.gz`.

XINBI GUARANTEE had a large outward transfer-time value in the last checked week before its identifier was published.

**USD 113,238.77, valued at each transfer time**; own-baseline weekly mean USD 2,913.55, maximum USD 51,418.52; 117 baseline weeks, active fraction 0.1795. Individual upper-tail p=0.008475.

Shorter-window outward USD at transfer times: {'1': 0, '3': 0}. Individual fake-date USD upper-tail p values: {'60': 0.10091743119266056, '90': 0.0380952380952381, '180': 0.010869565217391304}. Small fake-date p values weaken an anticipation interpretation for this case.

Exploratory selection, no individual multiplicity correction. Timestamped transfers and source prices are evidence for movement; neither their size nor their timing establishes a leak, intent, historical recipient control or unlawful conduct.

- [e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b](https://tronscan.org/#/transaction/e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b) (TRX, 2026-09-03T13:10:48Z); USD 93,600.16 at transfer time; price observation 2026-09-03T13:00:00Z.
- [04c18c61de4071d3b18e97958234dfc0463a6d15ea8058527ea733e8522d5c44](https://tronscan.org/#/transaction/04c18c61de4071d3b18e97958234dfc0463a6d15ea8058527ea733e8522d5c44) (TRX, 2026-09-05T10:32:36Z); USD 16,602.16 at transfer time; price observation 2026-09-05T10:00:00Z.
- [4e6e30e49c15642bc0fc2dcb94b8885c0930abe42745ddfaeaee134ebc61fc75](https://tronscan.org/#/transaction/4e6e30e49c15642bc0fc2dcb94b8885c0930abe42745ddfaeaee134ebc61fc75) (TRX, 2026-09-05T09:05:57Z); USD 2,764.44 at transfer time; price observation 2026-09-05T09:00:00Z.

ANSARALLAH had a large outward transfer-time value in the last checked week before its identifier was published.

**USD 110,368.93, valued at each transfer time**; own-baseline weekly mean USD 9,666.23, maximum USD 90,042.57; 64 baseline weeks, active fraction 0.4062. Individual upper-tail p=0.01538.

Shorter-window outward USD at transfer times: {'1': 0, '3': 40039.9926012996}. Individual fake-date USD upper-tail p values: {'60': 0.017543859649122806, '90': 0.019230769230769232, '180': 1.0}. Small fake-date p values weaken an anticipation interpretation for this case.

Exploratory selection, no individual multiplicity correction. Timestamped transfers and source prices are evidence for movement; neither their size nor their timing establishes a leak, intent, historical recipient control or unlawful conduct.

- [c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73](https://tronscan.org/#/transaction/c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73) (TRX, 2025-03-30T22:56:03Z); USD 20,045.99 at transfer time; price observation 2025-03-30T22:00:00Z.
- [457058ccd677ee51534647bc1bd5b3f98b33f40586cabe22894158a958e16cb8](https://tronscan.org/#/transaction/457058ccd677ee51534647bc1bd5b3f98b33f40586cabe22894158a958e16cb8) (TRX, 2025-03-30T12:42:54Z); USD 19,994.00 at transfer time; price observation 2025-03-30T12:00:00Z.
- [717a3a8c332fd249a3ac22015aa1db905b5b834a27438f8050491aad39b8e2c4](https://tronscan.org/#/transaction/717a3a8c332fd249a3ac22015aa1db905b5b834a27438f8050491aad39b8e2c4) (TRX, 2025-03-27T13:46:03Z); USD 15,003.00 at transfer time; price observation 2025-03-27T13:00:00Z.

Several BTC addresses listed under GRIMM, Matthew Simon moved funds close together before the identifier-publication date; these are one entity-level case.

**USD 1,341,131.60 gross address outflow volume, valued at each transfer time**, from 3 addresses under 1 OFAC entity; 3 distinct example transactions. Matched-baseline weekly mean USD 8,322.18, maximum USD 119,384.00, 46 common weeks; exploratory upper-tail p=0.02128.

Exploratory follow-up after ranking, not a registered primary entity test. Baselines are aligned to the same weekly endpoints and common history, rather than summing unequal lifetime means. Gross address outflow volume is not unique wealth. Common OFAC entity/action means this is one dependent case; the transactions do not establish notice, controller identity or a leak.

- [1b2f02023ec0e25d8000379f967a1424e661467c40108cbac1a0e2d2264a4314](https://mempool.space/tx/1b2f02023ec0e25d8000379f967a1424e661467c40108cbac1a0e2d2264a4314) (BTC, 2022-11-08T01:11:52Z); USD 426,201.88 at transfer time; price observation 2022-11-08T01:00:00Z.
- [30fd0ed35d44296ce3b9209845fb49f6b29e6151367d0edaca37cd816c4bb898](https://mempool.space/tx/30fd0ed35d44296ce3b9209845fb49f6b29e6151367d0edaca37cd816c4bb898) (BTC, 2022-11-08T01:33:38Z); USD 873,945.31 at transfer time; price observation 2022-11-08T01:00:00Z.
- [c0dacb7072d5c286de1fc2af5ba216f57e09bf35b55489e536a0cb8ef7db3173](https://mempool.space/tx/c0dacb7072d5c286de1fc2af5ba216f57e09bf35b55489e536a0cb8ef7db3173) (BTC, 2022-11-08T01:42:46Z); USD 40,984.41 at transfer time; price observation 2022-11-08T01:00:00Z.

### Actual versus own historical weeks

| Metric | Addresses | Connected clusters | Real mean | Baseline mean | Cluster rank score | One-sided p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| any_outflow | 887 | 59 | 0.05524 | 0.1535 | -0.09186 | 1 | 1 |
| balance_turnover | 378 | 48 | 78.15 | 1.482e+07 | -0.08086 | 1 | 1 |
| outflow_usd | 887 | 59 | 2.462e+04 | 1.292e+05 | -0.08721 | 1 | 1 |

USD means are USD per address-window at each transfer time; binary means are address shares, turnover means are unbounded gross outflow/opening balance ratios, not fractions of wealth removed. Tiny positive opening balances plus replenishment can make their arithmetic means enormous; use the registered ranks rather than these unstable magnitudes. Cluster score zero is the permutation center. Missing balance or price metrics are unavailable, not zero. P values are conditional diagnostics under the registered dependence model. Strata and cases are exploratory.

### Fake designation dates and shorter windows

| Shift before actual T (days) | Window (days) | Eligible addresses | Inactive addresses | Binary p | USD p | Balance p |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 7 | 887 | 214 | 1 | 1 | 1 |
| 0 | 3 | 888 | 353 | 1 | 1 | 0.9995 |
| 0 | 1 | 891 | 441 | 0.9998 | 0.9996 | 0.998 |
| 60 | 7 | 829 | 209 | 1 | 0.9999 | 0.9988 |
| 60 | 3 | 834 | 286 | 0.9999 | 0.9992 | 0.9903 |
| 60 | 1 | 835 | 408 | 0.9776 | 0.953 | 0.932 |
| 90 | 7 | 811 | 191 | 0.9951 | 0.9774 | 0.8405 |
| 90 | 3 | 813 | 323 | 1 | 0.9996 | 0.9822 |
| 90 | 1 | 813 | 405 | 0.9961 | 0.9931 | 0.9428 |
| 180 | 7 | 728 | 182 | 1 | 0.9998 | 0.996 |
| 180 | 3 | 731 | 261 | 0.9999 | 0.9983 | 0.9941 |
| 180 | 1 | 733 | 347 | 0.9991 | 0.9958 | 0.9904 |

Common-address placebo cohorts, active-history-only results, action-only/entity-only partitions and results excluding >10,000-transaction addresses are in `results/premove.json`. Program membership overlaps. Connected action/entity clustering is the primary analysis.

### Chain coverage

| Chain | Listed addresses | Trackable | Files/stubs | Readable wallet files | Complete wallet histories | Eligible 7-day |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ARB | 1 | 1 | 1 | 1 | 1 | 0 |
| BCH | 7 | 7 | 7 | 7 | 7 | 4 |
| BNB | 1 | 1 | 1 | 1 | 0 | 0 |
| BSC | 1 | 1 | 1 | 1 | 0 | 0 |
| BSV | 1 | 1 | 1 | 1 | 1 | 1 |
| BTC | 535 | 535 | 535 | 535 | 535 | 478 |
| BTG | 1 | 0 | 1 | 0 | 0 | 0 |
| DASH | 5 | 5 | 5 | 5 | 5 | 4 |
| DOGE | 2 | 2 | 2 | 2 | 2 | 2 |
| ETC | 1 | 1 | 1 | 1 | 1 | 0 |
| ETH | 217 | 216 | 216 | 125 | 125 | 111 |
| LTC | 13 | 13 | 13 | 13 | 13 | 13 |
| SOL | 4 | 4 | 4 | 4 | 0 | 0 |
| TRX | 341 | 341 | 341 | 341 | 340 | 273 |
| XMR | 12 | 0 | 12 | 0 | 0 | 0 |
| XRP | 1 | 1 | 1 | 1 | 1 | 1 |
| XVG | 1 | 1 | 1 | 1 | 0 | 0 |
| ZEC | 4 | 4 | 4 | 4 | 0 | 0 |

Chain-level details and per-address missing ranges/notes/reconciliation are retained in JSON. Full-history requirements exclude partial cohorts from inference even if a recent event window was fetched. Untrackable/private chains remain in the population table. No outflow found means within saved data checked.

### Most extreme individual cases

Sorted by the registered conservative individual upper-tail p, then descending transfer-time USD. This selection has no individual-discovery error correction and does not identify advance knowledge. Each case links OFAC action evidence, a complete baseline and example raw transactions in the JSON.

1. **GRIMM, Matthew Simon** — BTC `1LAh7PQwpd1uGiLHae5C5Xz9QXse3y2phq`, listed 2022-11-09. Seven-day outward value **USD 426,201.88 at each transfer time**; baseline mean USD 2,815.40, median USD 0.00, maximum USD 65,679.15 per prior week (186 weeks). Midrank 0.9973, conservative individual p=0.005348.
   - [1b2f02023ec0e25d8000379f967a1424e661467c40108cbac1a0e2d2264a4314](https://mempool.space/tx/1b2f02023ec0e25d8000379f967a1424e661467c40108cbac1a0e2d2264a4314) — 20.77381615 BTC, USD 426,201.88 at transfer 2022-11-08T01:11:52Z; price observed 2022-11-08T01:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/e0/e04413a88d60882fef4ffb74715464909abace423b246eb0ae821868e4431e5b-70175104779daa77.json.gz#response.transactions[0]`.

2. **XINBI GUARANTEE** — TRX `TAQPzv9941nVuTj4ng2vd6L11Re57r42pW`, listed 2026-09-09. Seven-day outward value **USD 113,238.77 at each transfer time**; baseline mean USD 2,913.55, median USD 0.00, maximum USD 51,418.52 per prior week (117 weeks). Midrank 0.9958, conservative individual p=0.008475.
   - [e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b](https://tronscan.org/#/transaction/e147c8a45f4c30658e6dd8489eb6d55a73eff7dc87750947301b6c606806af1b) — 93626.372811 USDT, USD 93,600.16 at transfer 2026-09-03T13:10:48Z; price observed 2026-09-03T13:00:00Z. Raw: `data/raw/tron/trc20/2c30dd9f719931271b4cd26fc98490482e95ef0e72863a5d9c8c5cb8eb0d6134.json.gz#/response/data/41`.
   - [04c18c61de4071d3b18e97958234dfc0463a6d15ea8058527ea733e8522d5c44](https://tronscan.org/#/transaction/04c18c61de4071d3b18e97958234dfc0463a6d15ea8058527ea733e8522d5c44) — 16600 USDT, USD 16,602.16 at transfer 2026-09-05T10:32:36Z; price observed 2026-09-05T10:00:00Z. Raw: `data/raw/tron/trc20/2c30dd9f719931271b4cd26fc98490482e95ef0e72863a5d9c8c5cb8eb0d6134.json.gz#/response/data/59`.
   - [4e6e30e49c15642bc0fc2dcb94b8885c0930abe42745ddfaeaee134ebc61fc75](https://tronscan.org/#/transaction/4e6e30e49c15642bc0fc2dcb94b8885c0930abe42745ddfaeaee134ebc61fc75) — 2764 USDT, USD 2,764.44 at transfer 2026-09-05T09:05:57Z; price observed 2026-09-05T09:00:00Z. Raw: `data/raw/tron/trc20/2c30dd9f719931271b4cd26fc98490482e95ef0e72863a5d9c8c5cb8eb0d6134.json.gz#/response/data/57`.

3. **GRIMM, Matthew Simon** — BTC `19GrL5jnUkGmHXVcraB1Etv5rXCANeLWpq`, listed 2022-11-09. Seven-day outward value **USD 873,945.31 at each transfer time**; baseline mean USD 35.82, median USD 0.00, maximum USD 3,008.48 per prior week (84 weeks). Midrank 0.9941, conservative individual p=0.01176.
   - [30fd0ed35d44296ce3b9209845fb49f6b29e6151367d0edaca37cd816c4bb898](https://mempool.space/tx/30fd0ed35d44296ce3b9209845fb49f6b29e6151367d0edaca37cd816c4bb898) — 42.59760482 BTC, USD 873,945.31 at transfer 2022-11-08T01:33:38Z; price observed 2022-11-08T01:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/35/35acca93f036d62a6b4a98b1b21e8b7e88f6aab2b891fbb4fdfca0ff993b9a61-75891ed9ffdd12f7.json.gz#response.transactions[0]`.

4. **HYDRA MARKET** — BTC `3P6PzdfETr4275Gn3veLkCyDxA1jV8fHKm`, listed 2022-04-05. Seven-day outward value **USD 1,041,424.21 at each transfer time**; baseline mean USD 251,674.52, median USD 228,818.00, maximum USD 575,590.95 per prior week (66 weeks). Midrank 0.9925, conservative individual p=0.01493.
   - [280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53](https://mempool.space/tx/280ce2cac30fa22050f383977c33fa417c94ab07c929479743db0b258fdf6e53) — 0.94884412 BTC, USD 43,585.10 at transfer 2022-04-04T20:28:58Z; price observed 2022-04-04T20:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/2f/2f75728ccb6c1932ce21fa57d5832a350b1c351d46a040893d5bdc2b0a317acb-fa713d0510841727.json.gz#response.transactions[78]`.
   - [ce85dbf04ef58ef3ac4570c15ec1d2403c4276e74f4dba3afc55f60935e86160](https://mempool.space/tx/ce85dbf04ef58ef3ac4570c15ec1d2403c4276e74f4dba3afc55f60935e86160) — 0.79979787 BTC, USD 36,908.57 at transfer 2022-04-01T15:47:11Z; price observed 2022-04-01T15:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/2f/2f75728ccb6c1932ce21fa57d5832a350b1c351d46a040893d5bdc2b0a317acb-fa713d0510841727.json.gz#response.transactions[98]`.
   - [c44a4367af181073aecce5afc74dc9d57ec1402c3227afeed8d9062c85635d0e](https://mempool.space/tx/c44a4367af181073aecce5afc74dc9d57ec1402c3227afeed8d9062c85635d0e) — 0.72988939 BTC, USD 33,273.12 at transfer 2022-03-31T20:56:45Z; price observed 2022-03-31T20:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/2f/2f75728ccb6c1932ce21fa57d5832a350b1c351d46a040893d5bdc2b0a317acb-fa713d0510841727.json.gz#response.transactions[110]`.

5. **ANSARALLAH** — TRX `TXEaKf4rT3rMoD3Vuqnuhwr6vLq6BL5t33`, listed 2025-04-02. Seven-day outward value **USD 110,368.93 at each transfer time**; baseline mean USD 9,666.23, median USD 0.00, maximum USD 90,042.57 per prior week (64 weeks). Midrank 0.9923, conservative individual p=0.01538.
   - [c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73](https://tronscan.org/#/transaction/c29b98d8e2422857fdcee533513dfeb226f91d05eba285fd8b482507bc7f0e73) — 20050 USDT, USD 20,045.99 at transfer 2025-03-30T22:56:03Z; price observed 2025-03-30T22:00:00Z. Raw: `data/raw/tron/trc20/9a35ecf99419525c870fcfc081eef8353f1bfeb4116056cff4d07100a14f378f.json.gz#/response/data/25`.
   - [457058ccd677ee51534647bc1bd5b3f98b33f40586cabe22894158a958e16cb8](https://tronscan.org/#/transaction/457058ccd677ee51534647bc1bd5b3f98b33f40586cabe22894158a958e16cb8) — 20000 USDT, USD 19,994.00 at transfer 2025-03-30T12:42:54Z; price observed 2025-03-30T12:00:00Z. Raw: `data/raw/tron/trc20/9a35ecf99419525c870fcfc081eef8353f1bfeb4116056cff4d07100a14f378f.json.gz#/response/data/22`.
   - [717a3a8c332fd249a3ac22015aa1db905b5b834a27438f8050491aad39b8e2c4](https://tronscan.org/#/transaction/717a3a8c332fd249a3ac22015aa1db905b5b834a27438f8050491aad39b8e2c4) — 15000 USDT, USD 15,003.00 at transfer 2025-03-27T13:46:03Z; price observed 2025-03-27T13:00:00Z. Raw: `data/raw/tron/trc20/9a35ecf99419525c870fcfc081eef8353f1bfeb4116056cff4d07100a14f378f.json.gz#/response/data/11`.

6. **HYDRA MARKET** — BTC `1PWRKxkR5AU7Tc9zPqjdhtu1eGW1QZzs4y`, listed 2022-04-05. Seven-day outward value **USD 913,341.01 at each transfer time**; baseline mean USD 90,365.58, median USD 35,988.40, maximum USD 784,787.51 per prior week (57 weeks). Midrank 0.9914, conservative individual p=0.01724.
   - [3783d4a964d3bc8a7a3e7b941716d185e2fa5258dd0cffe986ff6df9583a5ac8](https://mempool.space/tx/3783d4a964d3bc8a7a3e7b941716d185e2fa5258dd0cffe986ff6df9583a5ac8) — 3.33853204 BTC, USD 153,460.51 at transfer 2022-03-31T19:01:01Z; price observed 2022-03-31T19:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/6e/6e7383106c20b2520bc104f4f7945444fc2595cb9321aac9e96ffac6dd684312-334a099dbb9fdfd3.json.gz#response.transactions[34]`.
   - [89b393173fdc669188628c1085d92fc6919c27a708b4f22b5b352196b18d7c1b](https://mempool.space/tx/89b393173fdc669188628c1085d92fc6919c27a708b4f22b5b352196b18d7c1b) — 2.12849631 BTC, USD 101,125.93 at transfer 2022-03-29T17:09:08Z; price observed 2022-03-29T17:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/6e/6e7383106c20b2520bc104f4f7945444fc2595cb9321aac9e96ffac6dd684312-334a099dbb9fdfd3.json.gz#response.transactions[50]`.
   - [a755b0dde2ad1c5cb98bc18df1b9860e7f1124e07adb273e1be0af7e1a5731cf](https://mempool.space/tx/a755b0dde2ad1c5cb98bc18df1b9860e7f1124e07adb273e1be0af7e1a5731cf) — 2.10989319 BTC, USD 96,441.43 at transfer 2022-04-04T17:31:24Z; price observed 2022-04-04T17:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/6e/6e7383106c20b2520bc104f4f7945444fc2595cb9321aac9e96ffac6dd684312-334a099dbb9fdfd3.json.gz#response.transactions[5]`.

7. **SINBAD** — BTC `bc1qq7p0es3dv5hcynjjf40f2xjjr6qp5py47d2f6n847vduuq9gvnyq7y9ecd`, listed 2023-11-29. Seven-day outward value **USD 8,924.48 at each transfer time**; baseline mean USD 2,830.13, median USD 3,368.10, maximum USD 4,398.97 per prior week (47 weeks). Midrank 0.9896, conservative individual p=0.02083.
   - [bf0ba9d8a31df0c39e7114d767761c8b9c6bd48ae93ed69982363b7a54be99b9](https://mempool.space/tx/bf0ba9d8a31df0c39e7114d767761c8b9c6bd48ae93ed69982363b7a54be99b9) — 0.23506256 BTC, USD 8,924.48 at transfer 2023-11-28T22:30:59Z; price observed 2023-11-28T22:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/5c/5ca6413895391634898ec5e14afb7c52e78358ba558d4bce119b275ce6ad0c2b-1b3b44fd2e592aa9.json.gz#response.transactions[1]`.

8. **HYDRA MARKET** — BTC `3ES6pqCueDPCnC4hCqhhYuey6gyiRJZw6E`, listed 2022-04-05. Seven-day outward value **USD 1,873,974.76 at each transfer time**; baseline mean USD 820,581.88, median USD 824,198.47, maximum USD 1,974,575.54 per prior week (179 weeks). Midrank 0.9806, conservative individual p=0.02222.
   - [f2e8c35a9f5cabaa7e670717ecea5d14a81e614842b7d5f98447d4dc315c2693](https://mempool.space/tx/f2e8c35a9f5cabaa7e670717ecea5d14a81e614842b7d5f98447d4dc315c2693) — 5.81076818 BTC, USD 269,602.44 at transfer 2022-04-03T13:22:11Z; price observed 2022-04-03T13:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/b5/b50b97540dc18a6719a47301d45cdca5d05dd03a7162b1889a4aaede44c1a88a-1f2a2d244c21cf69.json.gz#response.transactions[27]`.
   - [011f722a5a879355b318c0d1ad7f807fadcb33a63dc9cb99b6d4c5cc4a7bfab3](https://mempool.space/tx/011f722a5a879355b318c0d1ad7f807fadcb33a63dc9cb99b6d4c5cc4a7bfab3) — 5.75046425 BTC, USD 268,727.87 at transfer 2022-04-02T13:02:07Z; price observed 2022-04-02T13:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/b5/b50b97540dc18a6719a47301d45cdca5d05dd03a7162b1889a4aaede44c1a88a-1f2a2d244c21cf69.json.gz#response.transactions[29]`.
   - [5726325d766caf4001c3d66e53a34b8f9527beace88dc095e9f70bc9dbaa932a](https://mempool.space/tx/5726325d766caf4001c3d66e53a34b8f9527beace88dc095e9f70bc9dbaa932a) — 4.52429146 BTC, USD 212,593.73 at transfer 2022-04-03T22:53:46Z; price observed 2022-04-03T22:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/b5/b50b97540dc18a6719a47301d45cdca5d05dd03a7162b1889a4aaede44c1a88a-1f2a2d244c21cf69.json.gz#response.transactions[23]`.

9. **ISIL KHORASAN** — TRX `TXR1nhqAek4c5Dq9EfjQLarcBWR9Jp6N7m`, listed 2026-07-01. Seven-day outward value **USD 4,464.52 at each transfer time**; baseline mean USD 0.00, median USD 0.00, maximum USD 0.00 per prior week (27 weeks). Midrank 0.9821, conservative individual p=0.03571.
   - [61636742cd6831c88753cf17b4b6ca2ee8714ae61cf1928cb3f72bad2511e5c6](https://tronscan.org/#/transaction/61636742cd6831c88753cf17b4b6ca2ee8714ae61cf1928cb3f72bad2511e5c6) — 3000 USDT, USD 2,996.76 at transfer 2026-06-28T04:43:45Z; price observed 2026-06-28T04:00:00Z. Raw: `data/raw/tron/trc20/fe754588a2ed5170706f3a2c15ba8c796c49d5f0fe25216e2f7fba367c57f2a6.json.gz#/response/data/21`.
   - [2c1ee2fa7c5fef2e3696cc697d869de096b67713caf0215f0a70f49533d74353](https://tronscan.org/#/transaction/2c1ee2fa7c5fef2e3696cc697d869de096b67713caf0215f0a70f49533d74353) — 653 USDT, USD 652.22 at transfer 2026-06-27T12:29:27Z; price observed 2026-06-27T12:00:00Z. Raw: `data/raw/tron/trc20/fe754588a2ed5170706f3a2c15ba8c796c49d5f0fe25216e2f7fba367c57f2a6.json.gz#/response/data/18`.
   - [82da3df936da0830411de572464b6309ca28b860a33b3899b044155483c6d66d](https://tronscan.org/#/transaction/82da3df936da0830411de572464b6309ca28b860a33b3899b044155483c6d66d) — 574 USDT, USD 573.24 at transfer 2026-06-30T15:18:12Z; price observed 2026-06-30T15:00:00Z. Raw: `data/raw/tron/trc20/fe754588a2ed5170706f3a2c15ba8c796c49d5f0fe25216e2f7fba367c57f2a6.json.gz#/response/data/25`.

10. **SOUTHFRONT** — BTC `3Gbs4rjcVUtQd8p3CiFUCxPLZwRqurezRZ`, listed 2021-04-15. Seven-day outward value **USD 66.72 at each transfer time**; baseline mean USD 16.18, median USD 0.00, maximum USD 988.21 per prior week (139 weeks). Midrank 0.9536, conservative individual p=0.05.
   - [21394aff5f641b1cf947bc5aea4692cd5f90167b6b133c9bb18e5787c0b7b698](https://mempool.space/tx/21394aff5f641b1cf947bc5aea4692cd5f90167b6b133c9bb18e5787c0b7b698) — 0.00089979 BTC, USD 56.69 at transfer 2021-04-14T15:50:08Z; price observed 2021-04-14T15:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/f3/f3250c480bf4aacb0811ea72a6ebfbf31a90ee02ab2751fa4cf933d032c5e385-33622a0b66089112.json.gz#response.transactions[2]`.
   - [641ad020361c3ccde601b89d4a4544089dafeaf7f19cbe85e0ffdb3f48166b30](https://mempool.space/tx/641ad020361c3ccde601b89d4a4544089dafeaf7f19cbe85e0ffdb3f48166b30) — 0.00017253 BTC, USD 10.03 at transfer 2021-04-10T00:28:24Z; price observed 2021-04-10T00:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/f3/f3250c480bf4aacb0811ea72a6ebfbf31a90ee02ab2751fa4cf933d032c5e385-33622a0b66089112.json.gz#response.transactions[4]`.

11. **ISIL KHORASAN** — TRX `TPCnxv28xNbvtAaEppddvnfkjQpaFeAkV3`, listed 2026-07-01. Seven-day outward value **USD 6,995.32 at each transfer time**; baseline mean USD 0.00, median USD 0.00, maximum USD 0.00 per prior week (12 weeks). Midrank 0.9615, conservative individual p=0.07692.
   - [2b9064b4111a3866aa482f94d63ba618fc8f790fc2752cbbcdb18e243f1c4d25](https://tronscan.org/#/transaction/2b9064b4111a3866aa482f94d63ba618fc8f790fc2752cbbcdb18e243f1c4d25) — 4000 USDT, USD 3,995.56 at transfer 2026-06-28T01:39:06Z; price observed 2026-06-28T01:00:00Z. Raw: `data/raw/tron/trc20/a2109098e050bd629373700d032b8ef2d5c30e67e086f6f743bc71b491afa13f.json.gz#/response/data/2`.
   - [5b5ecd9a38cc0b9cc0f8359d953faad21ce012e4ec9dd0b122fdf0cfdf749a49](https://tronscan.org/#/transaction/5b5ecd9a38cc0b9cc0f8359d953faad21ce012e4ec9dd0b122fdf0cfdf749a49) — 3000 USDT, USD 2,996.49 at transfer 2026-06-27T07:09:51Z; price observed 2026-06-27T07:00:00Z. Raw: `data/raw/tron/trc20/a2109098e050bd629373700d032b8ef2d5c30e67e086f6f743bc71b491afa13f.json.gz#/response/data/1`.
   - [ec32caea7d3ef710bfb5471f53039acb3d2ef8247e4db38551e36e8e983a4940](https://tronscan.org/#/transaction/ec32caea7d3ef710bfb5471f53039acb3d2ef8247e4db38551e36e8e983a4940) — 5.0722 TRX, USD 1.63 at transfer 2026-06-28T01:39:03Z; price observed 2026-06-28T01:00:00Z. Raw: `data/raw/tron/native/0021a1eafdc8c9f131c208f06b00119f8b825815bc14f142995060f6b03b1e8b.json.gz#/response/data/12`.

12. **GRIMM, Matthew Simon** — BTC `15yqWQ4sqr7jzCwDtZ3U1KaCa8WMEy7Mm2`, listed 2022-11-09. Seven-day outward value **USD 40,984.41 at each transfer time**; baseline mean USD 5,296.17, median USD 0.00, maximum USD 113,416.46 per prior week (46 weeks). Midrank 0.9255, conservative individual p=0.08511.
   - [c0dacb7072d5c286de1fc2af5ba216f57e09bf35b55489e536a0cb8ef7db3173](https://mempool.space/tx/c0dacb7072d5c286de1fc2af5ba216f57e09bf35b55489e536a0cb8ef7db3173) — 1.99765087 BTC, USD 40,984.41 at transfer 2022-11-08T01:42:46Z; price observed 2022-11-08T01:00:00Z. Raw: `data/raw/utxo/blockstream.info/fc/fce998fe42fd3f4e019d1785ff30ed34cb50981cd3ae538320f189e57ed1e661-99e6b21949904f96.json.gz#response[0]`.

13. **GARANTEX EUROPE OU** — ETH `0x7ff9cfad3877f21d41da833e2f775db0569ee3d9`, listed 2022-04-05. Seven-day outward value **USD 30,704.82 at each transfer time**; baseline mean USD 13,545.86, median USD 0.00, maximum USD 599,204.09 per prior week (125 weeks). Midrank 0.9167, conservative individual p=0.0873.
   - [0x6627296fac86150d71ce1b7723ed69ffc6ddc4985bb7f0138da5d6e6539a0a12](https://etherscan.io/tx/0x6627296fac86150d71ce1b7723ed69ffc6ddc4985bb7f0138da5d6e6539a0a12) — 11000 USDT, USD 11,004.40 at transfer 2022-03-30T10:34:47Z; price observed 2022-03-30T10:00:00Z. Raw: `data/raw/evm/etherscan/9277a53ff9e804591c2d6d4e.json.gz#/response/result/220`.
   - [0x0630f1c4c811141d11498a41aaf0e15d1d338f8b627b72ce091d52291594b9ae](https://etherscan.io/tx/0x0630f1c4c811141d11498a41aaf0e15d1d338f8b627b72ce091d52291594b9ae) — 8080 USDT, USD 8,083.23 at transfer 2022-03-29T09:55:49Z; price observed 2022-03-29T09:00:00Z. Raw: `data/raw/evm/etherscan/9277a53ff9e804591c2d6d4e.json.gz#/response/result/218`.
   - [0x71bdaa327bc9e6c83c19f789de47a3e091fb8fde3808e30659c184247c41981c](https://etherscan.io/tx/0x71bdaa327bc9e6c83c19f789de47a3e091fb8fde3808e30659c184247c41981c) — 7594 USDT, USD 7,596.28 at transfer 2022-03-31T09:43:31Z; price observed 2022-03-31T09:00:00Z. Raw: `data/raw/evm/etherscan/9277a53ff9e804591c2d6d4e.json.gz#/response/result/222`.

14. **SECONDEYE SOLUTION** — LTC `LQAhYwwK5AR1JQiQPr7vu8Pu4b6qcxxvNB`, listed 2021-04-15. Seven-day outward value **USD 538.55 at each transfer time**; baseline mean USD 459.23, median USD 120.78, maximum USD 25,216.87 per prior week (90 weeks). Midrank 0.9176, conservative individual p=0.08791.
   - [1a71089e42f6bb7d55f282763d3e1b258c82eaf3f24b2e5bcc9c1cef68649b9a](https://litecoinspace.org/tx/1a71089e42f6bb7d55f282763d3e1b258c82eaf3f24b2e5bcc9c1cef68649b9a) — 0.34828972 LTC, USD 97.01 at transfer 2021-04-14T20:18:11Z; price observed 2021-04-14T00:00:00Z. Raw: `data/raw/utxo/litecoinspace.org/8f/8f96e79e2c51890ccc2756e1bd95a6a020021fc21d68b2c31ed814049c8c19fb-9f95c746cfed7ba6.json.gz#response[6]`.
   - [b59cc48f18fd7a4b3c94c1f5e932de00bf64d971a5b06ba177605fe4a175da53](https://litecoinspace.org/tx/b59cc48f18fd7a4b3c94c1f5e932de00bf64d971a5b06ba177605fe4a175da53) — 0.35820928 LTC, USD 80.99 at transfer 2021-04-08T21:18:32Z; price observed 2021-04-08T00:00:00Z. Raw: `data/raw/utxo/litecoinspace.org/8f/8f96e79e2c51890ccc2756e1bd95a6a020021fc21d68b2c31ed814049c8c19fb-9f95c746cfed7ba6.json.gz#response[18]`.
   - [d70fa2b8c7131e0c03c9f0080546b391fef1bfb2c3739c4e6625d74d5dd352c0](https://litecoinspace.org/tx/d70fa2b8c7131e0c03c9f0080546b391fef1bfb2c3739c4e6625d74d5dd352c0) — 0.26999682 LTC, USD 61.05 at transfer 2021-04-08T12:19:04Z; price observed 2021-04-08T00:00:00Z. Raw: `data/raw/utxo/litecoinspace.org/8f/8f96e79e2c51890ccc2756e1bd95a6a020021fc21d68b2c31ed814049c8c19fb-9f95c746cfed7ba6.json.gz#response[20]`.

15. **CHATEX** — ETH `0x48549a34ae37b12f6a30566245176994e17c6b4a`, listed 2021-11-08. Seven-day outward value **USD 64,257.07 at each transfer time**; baseline mean USD 30,949.65, median USD 24,159.40, maximum USD 117,947.54 per prior week (36 weeks). Midrank 0.8514, conservative individual p=0.1622.
   - [0x9caf395a04247426386675f492cb0b7b1ddd7976744f067aa79179dab29f3bf2](https://etherscan.io/tx/0x9caf395a04247426386675f492cb0b7b1ddd7976744f067aa79179dab29f3bf2) — 3.870201906593753029 ETH, USD 17,318.11 at transfer 2021-11-06T09:03:58Z; price observed 2021-11-06T09:00:00Z. Raw: `data/raw/evm/etherscan/95ac3657eaeefe49ab77d6cc.json.gz#/response/result/461`.
   - [0xea1bdcf6d79f1a46cf836f5f3c089563dbceaa2e820c8762d6b03a86a516e077](https://etherscan.io/tx/0xea1bdcf6d79f1a46cf836f5f3c089563dbceaa2e820c8762d6b03a86a516e077) — 3.966189890277866584 ETH, USD 17,228.54 at transfer 2021-11-02T08:28:02Z; price observed 2021-11-02T08:00:00Z. Raw: `data/raw/evm/etherscan/95ac3657eaeefe49ab77d6cc.json.gz#/response/result/457`.
   - [0x98337fc7ba55fcde9e9455efea5049b207617d4f746f8f52f2e0e7f4e6f94442](https://etherscan.io/tx/0x98337fc7ba55fcde9e9455efea5049b207617d4f746f8f52f2e0e7f4e6f94442) — 3.279908181818199 ETH, USD 15,075.34 at transfer 2021-11-07T13:19:30Z; price observed 2021-11-07T13:00:00Z. Raw: `data/raw/evm/etherscan/95ac3657eaeefe49ab77d6cc.json.gz#/response/result/463`.

16. **XINBI GUARANTEE** — TRX `TTrHak4biV5ZtNwN1K8oi7916CjmeVVeH8`, listed 2026-09-09. Seven-day outward value **USD 1,089,159.44 at each transfer time**; baseline mean USD 784,243.57, median USD 832,758.60, maximum USD 1,412,515.58 per prior week (23 weeks). Midrank 0.8542, conservative individual p=0.1667.
   - [7e8c58a47bafe9f26327d89946d6b765879c0e441f898aeff604d71eacc1fc61](https://tronscan.org/#/transaction/7e8c58a47bafe9f26327d89946d6b765879c0e441f898aeff604d71eacc1fc61) — 73587 USDT, USD 73,575.96 at transfer 2026-09-08T04:27:24Z; price observed 2026-09-08T04:00:00Z. Raw: `data/raw/tron/trc20/46899ebb97f818fac42cc64f5e02bde3e8b8e1bba407460f8a7c741eded4b368.json.gz#/response/data/191`.
   - [ae42b8b715cc5187ec032ae9ef74be85246067163522d2fbca7a9b6480d4a25e](https://tronscan.org/#/transaction/ae42b8b715cc5187ec032ae9ef74be85246067163522d2fbca7a9b6480d4a25e) — 43066 USDT, USD 43,064.28 at transfer 2026-09-07T03:45:39Z; price observed 2026-09-07T03:00:00Z. Raw: `data/raw/tron/trc20/46899ebb97f818fac42cc64f5e02bde3e8b8e1bba407460f8a7c741eded4b368.json.gz#/response/data/153`.
   - [922cc7d965cec33f8bb8fea574c47ace7d4b3573d7a1b8497fcaf9941c5b35b8](https://tronscan.org/#/transaction/922cc7d965cec33f8bb8fea574c47ace7d4b3573d7a1b8497fcaf9941c5b35b8) — 42493 USDT, USD 42,490.88 at transfer 2026-09-07T05:46:12Z; price observed 2026-09-07T05:00:00Z. Raw: `data/raw/tron/trc20/46899ebb97f818fac42cc64f5e02bde3e8b8e1bba407460f8a7c741eded4b368.json.gz#/response/data/165`.

17. **SECONDEYE SOLUTION** — BTC `1NE2NiGhhbkFPSEyNWwj7hKGhGDedBtSrQ`, listed 2021-04-15. Seven-day outward value **USD 19,463.47 at each transfer time**; baseline mean USD 13,700.44, median USD 11,147.82, maximum USD 121,455.52 per prior week (90 weeks). Midrank 0.8297, conservative individual p=0.1758.
   - [efd124505da34d6e078ad854a1ebc2ce1d457f6d140ba28ae019308e08b5a063](https://mempool.space/tx/efd124505da34d6e078ad854a1ebc2ce1d457f6d140ba28ae019308e08b5a063) — 0.04902722 BTC, USD 2,921.33 at transfer 2021-04-11T16:11:30Z; price observed 2021-04-11T16:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/6c/6cc0af55a5fe0d3755971fb443fecac494a4d3de191414f67cbd43d69985e892-55c1e4c385fff8a1.json.gz#response.transactions[151]`.
   - [050f913756d20cab2c762231be8e0c69aa3b03c4c88de2a914b921a85f3d5c63](https://mempool.space/tx/050f913756d20cab2c762231be8e0c69aa3b03c4c88de2a914b921a85f3d5c63) — 0.02945761 BTC, USD 1,674.31 at transfer 2021-04-08T06:06:21Z; price observed 2021-04-08T06:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/6c/6cc0af55a5fe0d3755971fb443fecac494a4d3de191414f67cbd43d69985e892-55c1e4c385fff8a1.json.gz#response.transactions[256]`.
   - [ff7dcb3092a5925f8126ed1f62a8086ccca6406344b2391912c98dc4163b3446](https://mempool.space/tx/ff7dcb3092a5925f8126ed1f62a8086ccca6406344b2391912c98dc4163b3446) — 0.02126479 BTC, USD 1,221.41 at transfer 2021-04-08T14:04:21Z; price observed 2021-04-08T14:00:00Z. Raw: `data/raw/utxo/btc1.trezor.io/6c/6cc0af55a5fe0d3755971fb443fecac494a4d3de191414f67cbd43d69985e892-55c1e4c385fff8a1.json.gz#response.transactions[247]`.

18. **XINBI GUARANTEE** — TRX `TYq3iRujcBELXX89i9JY32UmLxcyZAJe7E`, listed 2026-09-09. Seven-day outward value **USD 1,348,924.99 at each transfer time**; baseline mean USD 846,799.62, median USD 732,807.11, maximum USD 2,322,601.06 per prior week (70 weeks). Midrank 0.8239, conservative individual p=0.1831.
   - [96e5aa7cfc2b15ea5400fdcc6d888bf999fcdb4e27f49bc6d5ed40b1861bd770](https://tronscan.org/#/transaction/96e5aa7cfc2b15ea5400fdcc6d888bf999fcdb4e27f49bc6d5ed40b1861bd770) — 106404.08 USDT, USD 106,400.89 at transfer 2026-09-07T07:50:57Z; price observed 2026-09-07T07:00:00Z. Raw: `data/raw/tron/trc20/8dd0e14d2fa1b80847e8185683d5ca9c9e7f8ca448fea1f9092c56406543940b.json.gz#/response/data/192`.
   - [bf02c1e9dc5acd8184007773272ded19a482bd07f99e7b683a189b58f9329de0](https://tronscan.org/#/transaction/bf02c1e9dc5acd8184007773272ded19a482bd07f99e7b683a189b58f9329de0) — 85573.2 USDT, USD 85,598.88 at transfer 2026-09-05T03:23:33Z; price observed 2026-09-05T03:00:00Z. Raw: `data/raw/tron/trc20/8dd0e14d2fa1b80847e8185683d5ca9c9e7f8ca448fea1f9092c56406543940b.json.gz#/response/data/153`.
   - [cd1ad8e288dc403b58e517f59d9117fb63c3691a7db1e5c5546259e728ac0684](https://tronscan.org/#/transaction/cd1ad8e288dc403b58e517f59d9117fb63c3691a7db1e5c5546259e728ac0684) — 67669 USDT, USD 67,685.92 at transfer 2026-09-05T05:41:42Z; price observed 2026-09-05T05:00:00Z. Raw: `data/raw/tron/trc20/8dd0e14d2fa1b80847e8185683d5ca9c9e7f8ca448fea1f9092c56406543940b.json.gz#/response/data/159`.

19. **CHATEX** — ETH `0x5512d943ed1f7c8a43f3435c85f7ab68b30121b0`, listed 2021-11-08. Seven-day outward value **USD 88,819.52 at each transfer time**; baseline mean USD 79,486.20, median USD 57,891.99, maximum USD 448,418.73 per prior week (27 weeks). Midrank 0.8036, conservative individual p=0.2143.
   - [0xcecdff3733663fc95822d51492cd9f8778e2bf2ae7c7f39186909aa05e96670a](https://etherscan.io/tx/0xcecdff3733663fc95822d51492cd9f8778e2bf2ae7c7f39186909aa05e96670a) — 4.223220048708543402 ETH, USD 18,648.64 at transfer 2021-11-02T12:10:35Z; price observed 2021-11-02T12:00:00Z. Raw: `data/raw/evm/etherscan/6ec3d4cf7410c66de91a4a4a.json.gz#/response/result/703`.
   - [0x53231e782d220bd360fbdd4f8266aad3fd1394c797bd620c759d63ebf4f3e42b](https://etherscan.io/tx/0x53231e782d220bd360fbdd4f8266aad3fd1394c797bd620c759d63ebf4f3e42b) — 3.872175906593753029 ETH, USD 17,326.94 at transfer 2021-11-06T09:01:48Z; price observed 2021-11-06T09:00:00Z. Raw: `data/raw/evm/etherscan/6ec3d4cf7410c66de91a4a4a.json.gz#/response/result/757`.
   - [0x0dfaf54dca3f8c67e8a9048b2f23993c64927cd498de07a6cf33e1c28e657906](https://etherscan.io/tx/0x0dfaf54dca3f8c67e8a9048b2f23993c64927cd498de07a6cf33e1c28e657906) — 3.969045890277866584 ETH, USD 17,240.94 at transfer 2021-11-02T08:23:41Z; price observed 2021-11-02T08:00:00Z. Raw: `data/raw/evm/etherscan/6ec3d4cf7410c66de91a4a4a.json.gz#/response/result/702`.

20. **SHEN, Xingbiao** — TRX `TEAqwfMhXLaomXhZ8KeMhx3njGmQEDnsUR`, listed 2023-10-03. Seven-day outward value **USD 4,747.25 at each transfer time**; baseline mean USD 3,321.64, median USD 0.00, maximum USD 25,710.28 per prior week (30 weeks). Midrank 0.7903, conservative individual p=0.2258.
   - [d1d5ddb90f4616c943ce60f118b03026194c1f2db0ce23ea2343a11618f09b88](https://tronscan.org/#/transaction/d1d5ddb90f4616c943ce60f118b03026194c1f2db0ce23ea2343a11618f09b88) — 3500 USDT, USD 3,496.50 at transfer 2023-09-28T14:47:03Z; price observed 2023-09-28T14:00:00Z. Raw: `data/raw/tron/trc20/8557daba9400566463e30ab95a1c5f53e346875670f0261a4332658d9f15a3b9.json.gz#/response/data/52`.
   - [a3a7c564097ee0409ac31fa09ea416010849435e1746e1cfd4bb73da320885e4](https://tronscan.org/#/transaction/a3a7c564097ee0409ac31fa09ea416010849435e1746e1cfd4bb73da320885e4) — 1251 USDT, USD 1,250.75 at transfer 2023-09-26T06:47:57Z; price observed 2023-09-26T06:00:00Z. Raw: `data/raw/tron/trc20/8557daba9400566463e30ab95a1c5f53e346875670f0261a4332658d9f15a3b9.json.gz#/response/data/50`.

### Interpretation, prior work and limitations

A higher pre-designation rank is a descriptive timing pattern, never proof of a leak. Seizures, indictments, earlier vendor reports, market regimes, service growth/decline, exchange failures and ordinary treasury sweeps can produce the same pattern. Saved `data/reference/cases.csv` and `vendor_claims.csv` provide context but cannot establish advance knowledge for a selected transaction. Historical recipient labels are unverified unless their validity dates are independently sourced.

The contribution beyond the saved Ethereum/Bitcoin prior art is the registered own-address weekly control with explicit 30-day buffer, clustered rank diagnostic, three fake-date checks, multi-chain source population and priced/coverage-aware abstention. Prior art already covers announcement anticipation; no claim of first discovery is made (see `docs/PRIOR_ART.md`).

Implementation note: turnover uses unit `ratio`, extending the results schema because the site contract reserves `share` for 0–1 fractions. Wrapped ETH/BTC use the ETH/BTC price proxy; wrapped-asset basis risk is not measured. These are encoding/valuation qualifications, not changes to the registered windows or tests.

The actual and fake-date cohorts can differ. The JSON includes a common-ID cohort; metric availability may still differ because a zero opening balance has no turnover denominator. A significant fake-date result weakens a pre-announcement interpretation. Common shocks and time dependence prevent exact causal inference even after action/entity clustering.

Balance share is deliberately strict: every recognised asset in a portfolio must have a nonnegative accounting path and a compatible independent ending balance. Missing fees, staking/rent adjustments, issuer burns or state snapshots at different blocks can suppress this metric. Native-coin UTXO outflow follows the fetcher’s net-debit/change convention, not the gross value of all transaction outputs; multisender fees are allocated by that source convention. Tron confirmed token events may lack block numbers; confirmation is supplied by the API route. XRP balance-change rows can include non-payment ledger operations.

Operational notes: standard-library implementation, offline price/label helpers only; no dependency installation or network access. Reviewed local helper imports and interpreter startup configuration; this constrained execution scope is not a global repository security claim. Only the three owned outputs are retained; atomic JSON saves use a short-lived `premove.json.*` sibling in results. No Git commit.

### Reproduce

```sh
.venv/bin/python scripts/analysis/premove.py --self-test
.venv/bin/python scripts/analysis/premove.py
.venv/bin/python scripts/analysis/premove.py --check
```

`--check` verifies hashes and recomputes the saved timeline inventory. It fails on a changed/missing/arrived input rather than silently adopting a live fetcher update. Regeneration adopts new histories without changing the script. JSON includes baseline windows, raw refs, price observations for case examples, and exclusions for every horizon/placebo.

This is research, not legal or compliance advice.
