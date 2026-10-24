# OFAC digital-currency ledger

Generated offline by `scripts/ledger/build_ledger.py`. Current OFAC XML issue date: **2026-10-21**. Research evidence, not legal or compliance advice.

## Rebuild and acceptance

Run from the repository root. Python standard library only; no additional dependencies:

```sh
.venv/bin/python scripts/ledger/build_ledger.py
.venv/bin/python scripts/ledger/build_ledger.py --check
.venv/bin/python scripts/ledger/build_ledger.py --fetch
```

`--check` performs no network requests or writes and compares all three CSVs and this report byte-for-byte. `--fetch` refreshes the official exports, pinned GitHub lists, sitemap, and newly discovered action pages; existing dated pages and immutable historical snapshots are reused. Repeated offline builds are byte-identical. Changed files use fsync plus atomic rename. No commits or pushes are made.

| Check | Result / unit |
| --- | --- |
| Current XML digital-currency features | 1066; all preserved, including duplicate features |
| Distinct current source address strings (canonical case) | 1050 |
| Distinct address strings among current ledger rows | 1050 |
| Current address–entity UID pairs / ledger rows | 1052 / 1052 |
| Current entity UID records | 106 |
| Current chain–address pairs | 1053 |
| All address–entity UID rows | 1185 |
| All distinct chain–address pairs | 1148 |
| All distinct entity UID records | 109 |
| OFAC action dates touching addresses | 75 |
| Rows with listing date + dated action URL | 1185/1185 (100.00%) |
| Unknown listing dates | 0 (0.00%; target <2%) |
| Missing recovered SDN UIDs | 0 |
| Source-text-reviewed random rows | 20 / 20 |
| Historical removed address–entity pairs | 133 |
| Trackable / untrackable address–entity rows | 1171 / 14 |
| Malformed literal source strings | 3 |
| Consolidated non-SDN digital-currency features | 0 |
| Current OFAC tickers in mapping table | 20 |
| SDN.XML vs advanced XML | exact UID/ticker/address multiset equality: 1066 features in each |


The source contains more entity links than distinct addresses, and more features than entity links. A literal requirement that the number of ledger *rows* equal distinct source addresses conflicts with the one-row-per-(address, SDN UID) contract. The equal distinct-address counts above are the completeness check; the additional entity links and ticker features are retained, not dropped to force equality.

## Source archive

All response bodies are gzip-compressed, content-addressed objects under `data/raw/ofac/objects/`. `data/raw/ofac/manifest.json` maps each logical request to its URL, resolved URL, fetch timestamp, HTTP status, byte count, SHA-256 of the **uncompressed response**, and `raw_ref`. `fetches.jsonl` retains previous fetch metadata; changed bytes remain available after refresh. CSV rows link to their XML/page objects; `listed_raw_ref` and `delisted_raw_ref` identify dated-page evidence.

| Source | Fetched UTC | SHA-256 | Raw reference |
| --- | --- | --- | --- |
| [sdn_advanced](https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML) | 2026-10-23T18:44:23+00:00 | 0d805bf58997908c8b5ba3233bc9b2b6d59bb04ea7881cfdc3c4c47d90d36e27 | data/raw/ofac/objects/0d805bf58997908c8b5ba3233bc9b2b6d59bb04ea7881cfdc3c4c47d90d36e27.gz |
| [sdn](https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML) | 2026-10-23T18:44:26+00:00 | 421c5f6ee841eb7c0e327eb0d6bdbe24cbb58091e3cbfd77d83dd41c7b5a5e08 | data/raw/ofac/objects/421c5f6ee841eb7c0e327eb0d6bdbe24cbb58091e3cbfd77d83dd41c7b5a5e08.gz |
| [consolidated_advanced](https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/CONS_ADVANCED.XML) | 2026-10-23T18:44:28+00:00 | dc3f61dce650a4661ff69d6c1847f0d5a90f2fa63951267af68fcfacdb6d8a75 | data/raw/ofac/objects/dc3f61dce650a4661ff69d6c1847f0d5a90f2fa63951267af68fcfacdb6d8a75.gz |


The saved sitemap scan enumerates **1391** action pages since 2018-11-28, with **0** fetch failures. **1391** dated pages are parsed (the cache also includes investigated seed URLs). The archive covers suffixed URLs such as `20240528_33`; guessing unsuffixed URLs alone misses real address additions. This establishes completeness within OFAC’s current sitemap, not a guarantee about unpublished or removed historical pages.

Archived OFAC SDN.XML bytes via the Internet Archive recover historical UID/name/program associations:

| Snapshot request | Raw reference |
| --- | --- |
| [historic_sdn_202208](https://web.archive.org/web/20220808155600id_/https://www.treasury.gov/ofac/downloads/sdn.xml) | data/raw/ofac/objects/6f4ace315344a04f0fa328ff6992e295e1de3d56ab4b8c137b256a2a04dbf1aa.gz |
| [historic_sdn_2023](https://web.archive.org/web/20230623105856id_/https://www.treasury.gov/ofac/downloads/sdn.xml) | data/raw/ofac/objects/bb96ab6e573acb80bac542f655bcb868bd50f45a17dd8aa5795ec4ede56508bc.gz |


## Schema and date rules

`data/ledger.csv` has one row per canonical address and SDN entity UID, preserving source casing in `address`. `ticker` and `chain` are representative values for compatibility; **use `tickers`, `chains`, and JSON `feature_records` for complete coverage**. In particular, one address is explicitly listed for ETH/ARB/BSC and one for ETH/ETC. `data/addresses.csv` expands these into separate chain–address rows. A shared address is also allowed under multiple entities. All advanced feature IDs remain in `source` and `feature_records`; the duplicated BLENDER.IO XBT feature is retained in the feature count.

Listing dates come from explicit addition sections or address differences between OFAC’s “-to-” before/after records. Unchanged addresses in a later update do not acquire that update date. Alias repetitions collapse to the XML UID. `listed_date` is first address publication for that entity lineage; `entity_record_listed_date` records when a replacement UID first lists it. `listing_events` retains each address addition/removal on the row. Each established date has method `recent_actions_page`, confidence `high`, a URL, and its saved page. A missing exact date would remain blank with method `unknown` and a reason.

`actions.csv` has one row per calendar action date. Multiple pages on that date have semicolon-separated URLs and titles. `n_addresses_added`/`n_addresses_removed` count distinct canonical address strings in explicit additions/deletions and before/after changes, not ticker features, aliases, entities, or first-ever-only publications. A same-day withdrawal/redesignation can appear in both columns; `n_addresses_added_and_removed` makes this overlap explicit. Administrative updates can have zero additions and zero removals.

## Current counts by OFAC ticker

| Ticker | XML features | Distinct addresses carrying ticker |
| --- | --- | --- |
| ARB | 1 | 1 |
| BCH | 7 | 7 |
| BNB | 1 | 1 |
| BSC | 1 | 1 |
| BSV | 1 | 1 |
| BTG | 1 | 1 |
| DASH | 5 | 5 |
| DOGE | 2 | 2 |
| ETC | 1 | 1 |
| ETH | 120 | 120 |
| LTC | 14 | 13 |
| SOL | 4 | 4 |
| TRX | 261 | 261 |
| USDC | 2 | 2 |
| USDT | 94 | 94 |
| XBT | 534 | 532 |
| XMR | 11 | 11 |
| XRP | 1 | 1 |
| XVG | 1 | 1 |
| ZEC | 4 | 4 |


Ticker counts overlap when the same address is listed for multiple assets. Feature counts sum to the XML feature total; distinct-address counts across tickers must not be summed.

## Current counts by program

| Program tag | Distinct addresses | Entity UID records |
| --- | --- | --- |
| CAATSA - RUSSIA | 2 | 2 |
| CYBER2 | 398 | 27 |
| CYBER3 | 6 | 3 |
| CYBER4 | 58 | 10 |
| DPRK2 | 1 | 1 |
| DPRK3 | 55 | 6 |
| DPRK4 | 67 | 5 |
| ELECTION-EO13848 | 57 | 6 |
| FTO | 142 | 2 |
| HRIT-IR | 15 | 1 |
| IFSR | 31 | 7 |
| ILLICIT-DRUGS-EO14059 | 154 | 18 |
| IRAN | 6 | 1 |
| IRAN-EO13902 | 8 | 2 |
| IRGC | 16 | 4 |
| NPWMD | 22 | 2 |
| RUSSIA-EO14024 | 35 | 11 |
| SDGT | 213 | 24 |
| SDNTK | 12 | 3 |
| TCO | 88 | 9 |
| UKRAINE-EO13661 | 2 | 1 |


Program counts overlap because an entry can carry several program tags. They are not additive.

## Ticker → chain → trackability

EVM hex is lowercased; Bitcoin/Litecoin bech32 is lowercased; base58 preserves case. Tron base58check and `41`-hex are converted to the same base58 canonical address; `tron_hex` preserves its equivalent hex form. No unlabelled controller identity is inferred. Native tickers identify their explicit chain. USDT/USDC use address format: `T…`/`41…` → TRX, `1…`/`3…`/`bc1…` → BTC (Omni), and `0x…` → ETH by convention. **A 20-byte EVM address cannot establish the EVM network by itself**: stablecoin EVM assignments have medium chain confidence. BNB `bnb1…` means Beacon Chain; a BNB `0x…` would mean BSC.

One explicit source-label conflict is preserved: WANG, Mingming (UID 45404) has `TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq` labelled **XBT** in both XML formats and the [2023-10-03 action](https://ofac.treasury.gov/recent-actions/20231003). It passes Tron base58check with version `41`, so its chain is **TRX**, while `ticker=XBT` remains unchanged. `source_ticker_mismatch=true`, the mapping rule, and medium confidence expose this source anomaly. It is a valid address with a conflicting ticker label, not a silently repaired address.

| Ticker | Chain | Trackable | Public history route / reason |
| --- | --- | --- | --- |
| ARB | ARB | true | https://arbiscan.io/ |
| BCH | BCH | true | https://blockchair.com/bitcoin-cash |
| BNB | BNB | true | https://explorer.bnbchain.org/ |
| BSC | BSC | true | https://bscscan.com/ |
| BSV | BSV | true | https://whatsonchain.com/ |
| BTG | BTG | false | No usable full-history public explorer identified for this chain |
| DASH | DASH | true | https://chainz.cryptoid.info/dash/ |
| DOGE | DOGE | true | https://dogechain.info/ |
| ETC | ETC | true | https://etc.blockscout.com/ |
| ETH | ETH | false / true | Malformed address: failed 20-byte hex shape; EIP-55 not checked; https://etherscan.io/ |
| LTC | LTC | true | https://litecoinspace.org/ |
| SOL | SOL | true | https://explorer.solana.com/ |
| TRX | TRX | true | https://tronscan.org/ |
| USDC | ETH | true | https://etherscan.io/ |
| USDT | BTC | true | https://mempool.space/docs/api/rest |
| USDT | ETH | true | https://etherscan.io/ |
| USDT | TRX | true | https://tronscan.org/ |
| XBT | BTC | true | https://mempool.space/docs/api/rest |
| XBT | TRX | true | https://tronscan.org/ |
| XMR | XMR | false | Malformed address: failed Monero shape; Keccak checksum not checked; Monero privacy prevents public address-level full-history observation |
| XRP | XRP | true | https://xrpscan.com/ |
| XVG | XVG | true | https://verge-blockchain.info/ |
| ZEC | ZEC | true | https://mainnet.zcashexplorer.app/ |


`trackable` means a public address-history route is identified; it does **not** assert any chain history has been collected or exhaustively validated by the ledger build. False rows remain in both CSVs. Monero is private; transparent Zcash is eligible and shielded/unified addresses would be excluded from public address history. Malformed addresses are false even on an otherwise trackable chain. BNB Beacon Chain’s historical explorer serves the listed address; its retirement must be considered by downstream timeline work.

Explorer checks are reproducible with `scripts/ledger/probe_explorers.py`. Saved provider pages are indexed by `explorer_*` in the raw manifest. CryptoID’s DOGE/BTG/XVG URLs returned a generic directory, so HTTP 200 was not treated as proof of coverage. Working alternatives were identified for DOGE, LTC, ZEC, and XVG. Bitcoin Gold’s old explorer hostname and Trezor hostname did not resolve, and the Guarda endpoint returned 404; BTG remains false until a usable provider is verified. TRX, BCH, BSC, and SOL have known public explorers but this environment encountered 401/403/429 or a browser challenge; API access, pagination, and the earliest available block still need downstream verification. No chain-flow result is claimed here.

## Malformed source values

| UID | Entity | Ticker | Address (literal) | Current? | Validation |
| --- | --- | --- | --- | --- | --- |
| 29702 | LIFSHITS, Artem Mikhaylovich | ETH | 0xa7e5d5a720f06526557c513402f2e6b5fa20b00 | false | 20-byte hex shape; EIP-55 not checked |
| 18647 | ISIL KHORASAN | XMR | 45ezvPejNsKYntjhyyeb7fbfzilsxYQozc5Ffseh8jPGW4JZQQVXykNTfK5uGFiij7Hp3qPv3T5HCR7F3Fnmz2mzE1aKQwo | false | Monero shape; Keccak checksum not checked |
| 29585 | KARASAVIDI, Dmitrii | XMR | 5be5543ff73456ab9f2d207887e2af87322c651ea1a873c5b25b7ffae456c320 | true | Monero shape; Keccak checksum not checked |


Shape/checksum validation is explicit per row. EIP-55 and Monero Keccak checksums are not claimed. The short LIFSHITS ETH value and the older ISIL KHORASAN XMR spelling are retained with their later removal/correction dates; no source typo is silently repaired.

## Removed addresses and replacement records

| UID | OFAC entry | Removed date | Address–entity rows | Action URL |
| --- | --- | --- | --- | --- |
| 18647 | ISIL KHORASAN | 2026-09-09 | 1 | https://ofac.treasury.gov/recent-actions/20260909 |
| 29702 | LIFSHITS, Artem Mikhaylovich | 2021-11-08 | 1 | https://ofac.treasury.gov/recent-actions/20211108 |
| 31811 | FAYZIMATOV, Farrukh Furkatovitch | 2026-08-24 | 1 | https://ofac.treasury.gov/recent-actions/20260824 |
| 33854 | CHATEX | 2024-01-11 | 1 | https://ofac.treasury.gov/recent-actions/20240111 |
| 38499 | TORNADO CASH | 2022-11-08 | 38 | https://ofac.treasury.gov/recent-actions/20221108 |
| 39796 | TORNADO CASH | 2025-03-21 | 90 | https://ofac.treasury.gov/recent-actions/20250321 |
| 56360 | SOKOLOVSKI, Rolan | 2025-11-24 | 1 | https://ofac.treasury.gov/recent-actions/20251124 |


Tornado Cash UID **38499** had 45 ticker features over **38 distinct addresses** in the August 2022 snapshot. OFAC withdrew that record on 2022-11-08 and added UID **39796** with **90 ETH addresses**. All 90 replacement-record addresses were removed on **2025-03-21**. The 38 old rows are not 38 additional unique addresses on top of the 90: 37 recur in the replacement, while `0x905b63Fff465B9fFBF41DeA908CEb12478ec7601` does not. Treasury’s delisting press release is also saved under `treasury_tornado_delisting` ([source](https://home.treasury.gov/news/press-releases/sb0057)).

Removal of an address feature does not imply that OFAC delisted its entity. LIFSHITS and ISIL KHORASAN include corrected strings; CHATEX and SOKOLOVSKI lose individual address features while their current entries remain. FAYZIMATOV’s deletion names the removed entity. The Beacon Chain address later appears under CRYPTO HOME DMCC, so its historical SOKOLOVSKI removal is not a present-day global delisting of that address.

## 0xB10C reconciliation

Current list comparison is pinned to `6ae2472c439b9bb2788f8df662052ae31854aa97` on the `lists` branch. **62 commits** and every dated patch are saved. Only public data files and diffs are read; upstream code is not executed. The earliest real address baseline is the commit explicitly described as a September 2022 squash; its 2021 author timestamp is not used as an address designation date.

OFAC-not-0xB10C: **3 ticker/address pairs**. 0xB10C-not-OFAC: **0 pairs**.

| Direction | Ticker | Address | Explanation |
| --- | --- | --- | --- |
| OFAC-not-0xB10C | BNB | bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23 | Ticker omitted by current upstream extraction support |
| OFAC-not-0xB10C | DOGE | DHzAVdEoL3PjGeLWNdEJwwMA1CeQ9J9Cpo | Ticker omitted by current upstream extraction support |
| OFAC-not-0xB10C | DOGE | DTqpKQ96rqkTvHcohQQd9BksmgRjasHgGo | Ticker omitted by current upstream extraction support |


Ticker differences for shared current addresses: **0**. Case-only differences are normalized for comparison; ticker labels from OFAC are never overwritten by the third-party list.

| History commit day (UTC) | Raw address deletions | Case-only changes | OFAC explanation |
| --- | --- | --- | --- |
| 2022-11-09 | 2 | 1 | 2022-11-08 withdrawal/redesignation; one case-only change |
| 2024-01-12 | 1 | 0 | CHATEX update on 2024-01-11 |
| 2025-03-22 | 90 | 0 | 90 Tornado Cash removals on 2025-03-21 |
| 2026-08-25 | 1 | 0 | FAYZIMATOV deletion on 2026-08-24 |
| 2026-09-10 | 1 | 0 | ISIL KHORASAN spelling correction on 2026-09-09 |


All non-case historical removals correspond to retained ledger rows with dated OFAC removal evidence. The pre-squash LIFSHITS correction and unsupported BNB/SOKOLOVSKI removal were found by scanning OFAC pages, demonstrating why the GitHub history alone is insufficient.

## Random source-text verification

Uniform sample without replacement from 1185 sorted ledger rows; seed `20261023`. **20 rows** were directly reviewed against the saved Recent Actions entry text during this task. This is a computational source-text review, not an independent external human audit. Selections, exact excerpts, raw references, and review notes are retained in `scripts/ledger/manual_verification.json`. The build revalidates each saved quote against its raw page.

| # | UID / entry | Address | First publication / page | What OFAC says |
| --- | --- | --- | --- | --- |
| 1 | 55505 / CHEN, Zhi | bc1qu4p4eynzu8vwwcv0yxq74gth00exjyech05uf0 | [2025-10-30](https://ofac.treasury.gov/recent-actions/20251030) | update_after: “…uj; alt. Digital Currency Address - XBT bc1qu4p4eynzu8vwwcv0yxq74gth00exjyech05uf0; alt. Digital Currency Address - XBT bc1qw0pswznckx7s6tjmd2f5hrx4q6kc5nyrdxku50; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. Address added in the October 30 update, after the October 14 entity designation. |
| 2 | 53033 / PARSARAD, Behrouz | bc1qyqvyupkpl6tm60zdecef925y220ssjuagpxsm0 | [2025-03-04](https://ofac.treasury.gov/recent-actions/20250304) | addition: “…jy; alt. Digital Currency Address - XBT bc1qyqvyupkpl6tm60zdecef925y220ssjuagpxsm0; alt. Digital Currency Address - XBT bc1q45cxufu7x6s5v9adzm9t38k80gwawse75xffwe; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 3 | 53033 / PARSARAD, Behrouz | bc1q45cxufu7x6s5v9adzm9t38k80gwawse75xffwe | [2025-03-04](https://ofac.treasury.gov/recent-actions/20250304) | addition: “…m0; alt. Digital Currency Address - XBT bc1q45cxufu7x6s5v9adzm9t38k80gwawse75xffwe; alt. Digital Currency Address - XBT bc1qmzmx8res2fgzd2wttyvf2ajqqqtcnxxrgkqc2t; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 4 | 45404 / WANG, Mingming | TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq | [2023-10-03](https://ofac.treasury.gov/recent-actions/20231003) | addition: “…vz; alt. Digital Currency Address - XBT TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq; Digital Currency Address - USDT 0xfac583c0cf07ea434052c49115a4682172ab6b4f; National ID …” Literal address and ticker occur under the named OFAC entry on the stated dated page. OFAC prints XBT; its valid Tron address format is preserved as a source-label conflict. |
| 5 | 29702 / LIFSHITS, Artem Mikhaylovich | 0xa7e5d5a720f06526557c513402f2e6b5fa20b008 | [2021-11-08](https://ofac.treasury.gov/recent-actions/20211108) | update_after: “…0e; alt. Digital Currency Address - ETH 0xa7e5d5a720f06526557c513402f2e6b5fa20b008; Phone Number 79110354982; Digital Currency Address - LTC Leo3j36nn1JcsUQruytQhFUdCdCH5YH…” Literal address and ticker occur under the named OFAC entry on the stated dated page. Corrected 20-byte address first appears in the after-state; the shorter prior string is a separate historical row. |
| 6 | 47682 / KONDRATIEV, Ivan Gennadievich | bc1qn6segn8km4nfdp9vueu6msfjsaxaqgun9h60n9 | [2024-02-20](https://ofac.treasury.gov/recent-actions/20240220) | addition: “…xr; alt. Digital Currency Address - XBT bc1qn6segn8km4nfdp9vueu6msfjsaxaqgun9h60n9; alt. Digital Currency Address - XBT bc1qx9upga7f09tsetqf78wa3qrmcjar58mkwz6ng6; Digital …” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 7 | 53033 / PARSARAD, Behrouz | 84AwzjeFWXNEuhj8LWinXo93AqYr6wS8ZcnaBCoGhrL7EtvBMBovdhiUSV9xLhjrPA8t64hYSaMc8bHtWXoV9129EHUjU62 | [2025-03-04](https://ofac.treasury.gov/recent-actions/20250304) | addition: “…5M; alt. Digital Currency Address - XMR 84AwzjeFWXNEuhj8LWinXo93AqYr6wS8ZcnaBCoGhrL7EtvBMBovdhiUSV9xLhjrPA8t64hYSaMc8bHtWXoV9129EHUjU62; alt. Digital Currency Address - XMR 87XWTP9tBECHXCwbyMK1KENoy4GeXkRviNzmhNc5Pvo5ExZ1QXjt…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 8 | 39796 / TORNADO CASH | 0xCEe71753C9820f063b38FDbE4cFDAf1d3D928A80 | [2022-11-08](https://ofac.treasury.gov/recent-actions/20221108) | addition: “…85; alt. Digital Currency Address - ETH 0xCEe71753C9820f063b38FDbE4cFDAf1d3D928A80; alt. Digital Currency Address - ETH 0xffbac21a641dcfe4552920138d90f3638b3c9fba; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 9 | 47682 / KONDRATIEV, Ivan Gennadievich | 15cRqR3TXS1JehBGWERuxFE8NhWZzfoeeU | [2024-02-20](https://ofac.treasury.gov/recent-actions/20240220) | addition: “…JM; alt. Digital Currency Address - XBT 15cRqR3TXS1JehBGWERuxFE8NhWZzfoeeU; alt. Digital Currency Address - XBT 1A7SKE2dQtezLktCY8peLsdAtkqxV9r1dC; alt. Digital Cur…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 10 | 24003 / MESRI, Behzad | TAbbVaBKgH4VBLXgWqACuwoKF4cH1HinQh | [2026-08-24](https://ofac.treasury.gov/recent-actions/20260824) | update_after: “…175Be91; Digital Currency Address - TRX TAbbVaBKgH4VBLXgWqACuwoKF4cH1HinQh; alt. Digital Currency Address - TRX TEsxMcVocweTM82Mdmc5diKC6qyCWqSpPv (individual) [HRI…” Literal address and ticker occur under the named OFAC entry on the stated dated page. The before-state lacks this address; entity designation dates are not substituted. |
| 11 | 36216 / HYDRA MARKET | 1HuYfoEwsfHgZiRhbhJrCd5ST3iksa8KEx | [2022-04-05](https://ofac.treasury.gov/recent-actions/20220405) | addition: “…x3; alt. Digital Currency Address - XBT 1HuYfoEwsfHgZiRhbhJrCd5ST3iksa8KEx; alt. Digital Currency Address - XBT 1J9wJH2bamZVxscXAvoDH4jvtGKb7sYFDm; alt. Digital Cur…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 12 | 30518 / SECONDEYE SOLUTION | LeKvNdNEzgQkzVVnRdV3fAu2DSF1nLsNw6 | [2021-04-15](https://ofac.treasury.gov/recent-actions/20210415) | addition: “…9L; alt. Digital Currency Address - LTC LeKvNdNEzgQkzVVnRdV3fAu2DSF1nLsNw6; Digital Currency Address - BCH 18M8bJWMzWHDBMxoLqjHHAffdRy4SrzkfB [CYBER2] [ELECTION-EO1…” Literal address and ticker occur under the named OFAC entry on the stated dated page. The same page lists this address under both RAZA and SECONDEYE SOLUTION; this quote is from SECONDEYE. |
| 13 | 33854 / CHATEX | bc1q4rzdtlt0uslyw86cp29sctl6ct29g9a95cuup7pn5md9ddj7xgmqpp5m73 | [2021-11-08](https://ofac.treasury.gov/recent-actions/20211108) | addition: “…hD; alt. Digital Currency Address - XBT bc1q4rzdtlt0uslyw86cp29sctl6ct29g9a95cuup7pn5md9ddj7xgmqpp5m73; alt. Digital Currency Address - XBT 39KQvziHwUe2vddbpfC5WkQEV72qbQhxuh; alt. Digital Cur…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 14 | 27307 / LAZARUS GROUP | 0x53b6936513e738f44FB50d2b9476730C0Ab3Bfc1 | [2022-04-22](https://ofac.treasury.gov/recent-actions/20220422) | update_after: “…73; alt. Digital Currency Address - ETH 0x53b6936513e738f44FB50d2b9476730C0Ab3Bfc1; Secondary sanctions risk: North Korea Sanctions Regulations, sections 510.201 and 510.21…” Literal address and ticker occur under the named OFAC entry on the stated dated page. The before-state lacks this address; entity designation dates are not substituted. |
| 15 | 39796 / TORNADO CASH | 0x9AD122c22B14202B4490eDAf288FDb3C7cb3ff5E | [2022-08-08](https://ofac.treasury.gov/recent-actions/20220808) | addition: “…2a; alt. Digital Currency Address - ETH 0x9AD122c22B14202B4490eDAf288FDb3C7cb3ff5E; alt. Digital Currency Address - ETH 0x905b63Fff465B9fFBF41DeA908CEb12478ec7601; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. First published under UID 38499; UID 39796 is the November replacement. |
| 16 | 57978 / RASHEVSKYI, Dmytro | 0x2C7DcD774b33e10367F7d6385479e04F97d179dc | [2026-07-13](https://ofac.treasury.gov/recent-actions/20260713) | addition: “…f8; alt. Digital Currency Address - ETH 0x2C7DcD774b33e10367F7d6385479e04F97d179dc; Digital Currency Address - LTC LcP1DumXkNJbBtSYD3XxAfsJ2nZR5hLdpM; alt. Digital Currency…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 17 | 55505 / CHEN, Zhi | bc1qw75cxmxz4e2v265mue9wmqgq2m0qdyr25l2ufl | [2025-10-30](https://ofac.treasury.gov/recent-actions/20251030) | update_after: “…2x; alt. Digital Currency Address - XBT bc1qw75cxmxz4e2v265mue9wmqgq2m0qdyr25l2ufl; alt. Digital Currency Address - XBT bc1q7des766x6c0zkycz6dz6rfv066n3fcg4kggtrt; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. Address added in the October 30 update, after the October 14 entity designation. |
| 18 | 57978 / RASHEVSKYI, Dmytro | t1LHesgnkapziGQCJtrfZWYXhyjfTVo1dvh | [2026-07-13](https://ofac.treasury.gov/recent-actions/20260713) | addition: “…6EziaL1; Digital Currency Address - ZEC t1LHesgnkapziGQCJtrfZWYXhyjfTVo1dvh; Digital Currency Address - DASH XcuGqRfrR85zyDrzVr1gSL5RNjwwpbu2KS; alt. Digital Currenc…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 19 | 39796 / TORNADO CASH | 0xaf8d1839c3c67cf571aa74B5c12398d4901147B3 | [2022-11-08](https://ofac.treasury.gov/recent-actions/20221108) | addition: “…98; alt. Digital Currency Address - ETH 0xaf8d1839c3c67cf571aa74B5c12398d4901147B3; alt. Digital Currency Address - ETH 0x6Bf694a291DF3FeC1f7e69701E3ab6c592435Ae7; alt. Dig…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |
| 20 | 36216 / HYDRA MARKET | 1B11Ezqg3AXjFhMdRq5UpPDpNyriYNVtkn | [2022-04-05](https://ofac.treasury.gov/recent-actions/20220405) | addition: “…dJ; alt. Digital Currency Address - XBT 1B11Ezqg3AXjFhMdRq5UpPDpNyriYNVtkn; alt. Digital Currency Address - XBT 16SPDQFFzgsoNSPiFFTfS8Dw8LLXqia4oc; alt. Digital Cur…” Literal address and ticker occur under the named OFAC entry on the stated dated page. |


## Remaining limits

The current ledger is exhaustive against both saved official SDN XML formats. Historical coverage is exhaustive over the downloaded sitemap pages and saved list diffs, not a claim about pages OFAC no longer exposes. All currently known row dates and historical UIDs are resolved. Stablecoin EVM chain inference, provider accessibility, address-level full-history pagination, and three malformed strings remain explicit limitations. The ledger documents identity/action evidence and trackability; separate analyses cover balances, flows, freezes and prices.
