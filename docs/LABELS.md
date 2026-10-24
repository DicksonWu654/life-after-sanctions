# Public destination labels

Data as of **2026-10-23**. Label claims are exact chain/address matches. They are leads about a service role, rather than proof of control, knowledge or unlawful conduct. Historical validity is often unknown.

## Redistribution decisions

Saved licence notices in `data/labels/licenses/` and source metadata in `data/labels/sources.json` were reviewed for this release. The public export includes only sources with established permission and official US-government factual records. MIT and Apache notices are retained. Across is omitted conservatively because its Business Source License is not a general open-data redistribution grant for this snapshot. Sources with no established redistribution licence are omitted even where they publish factual address tags.

| Source | Saved terms | Public lookup rows |
|---|---|---|
| brian | MIT | Included |
| daws | MIT | Included |
| tornado | MIT | Included |
| railgun | MIT | Included |
| hop | MIT | Included |
| wormhole | Apache-2.0 | Included |
| across | BUSL-1.1; change to GPL-3.0-or-later on 2027-07-27 (or earlier per license) | Omitted |
| op_registry | MIT | Included |
| arbitrum | Apache-2.0 | Included |
| ofac | US government sanctions facts; no third-party dataset license asserted | Included |
| tronscan | No explicit open-data redistribution license found; public API facts only | Omitted |
| walletexplorer | No explicit open-data redistribution license found; public API facts only | Omitted |
| uniswap | No license established for these web pages; factual contract addresses only | Omitted |
| sun | No license established for these web pages; factual contract addresses only | Omitted |
| stargate | No license established for these web pages; factual contract addresses only | Omitted |
| base | No license established for these web pages; factual contract addresses only | Omitted |
| avalanche_bridge | No license established for these web pages; factual contract addresses only | Omitted |
| etherscan_public | No open-data redistribution license established; factual name tags only | Omitted |
| thorchain | No open-data redistribution license established for the API response; factual addresses only | Omitted |

The base public table is gzip-compressed as `data/labels/labels.csv.gz`; the supplemental CSV is small enough to remain plain text.

## Table scope

| Table | Original source claims | Public source claims | Omitted claims |
|---|---:|---:|---:|
| `data/labels/labels.csv` | 67,609 | 66,349 | 1,260 |
| `data/labels/labels_extra.csv` | 38 | 14 | 24 |

The supplemental table retains the 14 official factual claims (`r2_ofac`) and omits explorer/cluster tags without established permission. The source manifest includes only redistributable lookup sources; the export-specific source decisions and exact counts are also saved in `scripts/release/LABEL_LICENSES.json`. Raw label databases, SQLite indexes, bulk destination-review tables and non-redistributable source blobs are excluded.

## Research classification and coverage

The published aggregate flow statistics describe the original research classification, which used additional public-source leads. Licence filtering of the lookup does not recalculate those aggregates. Restricted per-address source claims are removed from nested result records; their classification scope is documented rather than presented as a redistributable database. Short sourced research discussion retains its citations. Rebuilding after acquisition can produce a different label set and different aggregates.

An address may have several source claims. Chain aliases and exact contract/asset identities matter. A generic exchange name does not establish a deposit or hot-wallet role; conflicting roles remain unlabelled. Matching an OFAC-listed address requires source validity at the transfer time. Unknown-label destinations are not evidence that funds disappeared. Historical service validity, retirement, address reuse, exchange-scale histories and unequal per-chain labelling limit interpretation.

See `docs/analysis/FLOWS.md` for the first-hop and temporal-path rules, `docs/COVERAGE.md` for chain gaps and `scripts/labels/` for collection, role mapping and lookup code. Source URLs and raw references remain in every retained claim. Full source validation needs the omitted raw cache; `make verify` checks the public subset and manifest.
