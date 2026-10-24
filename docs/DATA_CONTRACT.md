# Site data contract (site/data/*.json)

The analysis pipeline writes these files via `scripts/export_site.py`; the static site reads only these. The public snapshot includes real `site/data/` files. Development fixtures are excluded.

Every number object carries its unit; every USD figure carries `valued_at` (ISO date or datetime UTC).
`{"value": 123.4, "unit": "usd", "valued_at": "2026-10-23"}`; units: `addresses`, `entities`, `actions`, `usd`,
`native:<TICKER>`, `days`, `hours`, `share` (0–1), `events`.

## meta.json
`{ "last_refreshed_utc", "ofac_list_published_utc", "counts": {addresses, entities, actions, chains, trackable_addresses, untrackable_addresses}, "coverage": [{chain, addresses, trackable, complete_history, notes}], "disclaimer_md" }`

## headline.json — big-number cards (ordered, most shareable first)
`[{ "id", "big": {value, unit, valued_at?}, "sentence", "detail_md", "example_txs": [{chain, hash, explorer_url}], "finding_ref" }]`

## cases.json — famous case timelines (5–10)
`[{ "id", "name" (as OFAC names it), "program", "designated", "press_release_url", "chains": [], "one_liner",
   "addresses": [address ids], "events": [{ "date", "kind": designation|first_outflow|freeze|burn|delisting|inflow|mixer|exchange|other, "label", "amount"?: {value, unit, valued_at}, "tx"?: {chain, hash, explorer_url}, "source_url"? }],
   "today": { "balance_usd": {value, unit, valued_at}, "status_sentence" } }]`

## programs.json — world/program map
`[{ "program" (e.g. CYBER2, DPRK3, SDGT, RUSSIA-EO14024), "label" (plain English), "countries": [ISO-3166 alpha-3 linked by OFAC entity addresses/nationality], "addresses", "entities", "value_at_designation_usd": {…}, "value_today_usd": {…}, "share_moved_after": {value, unit:"share"} }]`

## sankey.json — where the money went (post-designation outflows)
`{ "unit": "usd", "valued_at": "at transfer time", "nodes": [{id, label, kind: program|chain|destination_class}], "links": [{source, target, value}], "hop_rule", "notes" }`
Destination classes: mixer, bridge, dex, cex_deposit, other_sanctioned, unlabelled, still_there, frozen.

## freezes.json — Tether vs Circle
`{ "points": [{ issuer: tether|circle, chain, address, lag_hours (signed; negative = issuer first), amount_frozen: {value, unit:"usd", valued_at}, burned: bool, ofac_action_date, freeze_tx }], "summary": [{issuer, chain, sanctioned_addresses_holding_token, frozen, share_frozen, median_lag_hours, p90_lag_hours, usd_frozen}] }`

## addresses.json — explorer index (small rows; details lazy-loaded)
`[{ "id" (chain:address), "chain", "address", "ticker", "entities": [{uid, name}], "programs": [], "listed": date, "delisted"?: date, "trackable": bool, "untrackable_reason"?, "balance_at_listing_usd", "balance_today_usd", "moved_after": bool|null, "first_outflow_days"?: number, "frozen": bool, "flags": [] }]`

## address/<chain>/<address>.json — per-address timeline
`{ "id", ...index row, "checkpoints": [{label: "T-7d"|"T"|"T+7d"|"T+30d"|"T+365d"|"today", "time", "balances": [{asset, native, usd, valued_at}]}], "events": [{time, kind: in|out|freeze|burn|designation|delisting, asset, amount, usd, valued_at, counterparty, counterparty_label?, label_source?, tx, explorer_url, class?: real|dust|poisoning}], "sources": [url…], "raw_refs": [path…] }`

## Interpretation rules
Research, not legal advice. "Received funds from a sanctioned address" is a factual on-chain statement, not an
accusation; exchanges may have frozen or reported funds. Labels are leads. "No outflow found" = within data checked.
Name only what OFAC names.

## Additions agreed with the site build (2026-10-23)
- Array files (headline, cases, programs, addresses) are plain JSON arrays in site/data/ (fixtures wrap them as `{fixture:true, items:[...]}`).
- addresses.json rows add `moved_before_designation: bool|null`, `explorer_url` (address page), `assets_today: [{asset, native, usd, valued_at}]`. `first_outflow_days` is signed; negative = before designation.
- programs.json rows add `country_addresses: {ISO3: n_addresses}` for a true address-count choropleth.
- cases.json `today` adds `covers` (one line: which addresses/assets the balance covers).
- sankey.json node ids end in the class name (mixer, bridge, dex, cex_deposit, other_sanctioned, unlabelled, still_there, frozen); program→ and chain→ link sets are alternative views of the same dollars, never summed.

## Public CSV dictionary

All CSVs use UTF-8 and a header row. Missing observations remain blank/null. `source_url` is a public source; `raw_ref` identifies a source/request to re-fetch, with an optional original response locator after `#`; raw API captures are omitted for size. Those responses are reacquired separately; see the request index and `docs/PIPELINE.md`.

| File | Row key and principal fields |
|---|---|
| `data/ledger.csv` | Address–SDN entity UID; `address`, `address_normalized`, `ticker`, `chain`, `sdn_uid`, `sdn_name`, `sdn_type`, `programs`, `listed_date`, `listed_action_url`, `listed_action_title`, `delisted_date`, `delisted_action_url`, `trackable`, `untrackable_reason`, `source`. Extended `tickers`, `chains` and `feature_records` preserve multiple memberships. |
| `data/addresses.csv` | Distinct `(chain, address_normalized)`; `first_listed_date`, entity UIDs, programs, trackability, listing/removal provenance. Chain aliases stay separate. |
| `data/actions.csv` | Action-date record and official source URL; address-feature removal differs from entity delisting. |
| `data/freezes.csv` | `(chain, token, transaction_hash, log_index)`; issuer, address, blacklist/unblacklist/destruction action, timestamp, block, native amount when known and raw evidence. These are issuer-wide event logs, before OFAC matching. |
| `data/labels/labels.csv`, `labels_extra.csv` | Exact chain/address source claims; `label`, `class`, `entity_name`, `source_id`, `source_url`, `raw_ref`, `evidence_locator`, `license`, confidence and validity dates. Multiple claims can coexist; empty validity dates mean unknown. Public rows are licence-filtered. |
| `data/prices/manifest.csv` | Source URLs and inventory of locally cached price series, omitted from the public export. USD results retain their stated valuation times; fetch with `scripts/prices/price.py`. |
| `data/verify/*.csv`, `data/audit/*.csv` | Independent inventory, event or balance checks with source and raw evidence. Each table retains its own sampling/cohort fields. |
| `data/derived/*.csv.gz` | Compressed calculation detail, where below the release size limit. Large pre-listing JSON row detail is in `premove_address_results.json.gz`; summary JSON retains a reference. |

`results/*.json` carry units, valuation times, rules and coverage. Public result hashes describe release bytes; original input hashes remain provenance and may reference intentionally omitted caches. Licence filtering removes restricted nested lookup claims without recalculating the historical aggregate research.
