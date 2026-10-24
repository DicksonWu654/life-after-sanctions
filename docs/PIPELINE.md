# Reproducing the snapshot

Data as of **2026-10-23**. Updates are explicit: run `scripts/pipeline.py refresh` and review the resulting research before publishing. No schedule is installed.

## Included-data checks

Use Python 3.11+ on Linux and GNU Make. Create `.venv` with `uv venv .venv`, then `uv pip install -r requirements.txt`. Core research and release checks use the standard library.

- `make verify` validates explicit FINDINGS numeric tags and rendered rounding against saved result JSON and the independent freeze CSV. It checks site source hashes, address counts and detail files, required assets, licences, the release manifest, and the public-text gate.
- `make build` verifies and copies the saved static publication to `build/`. It needs no network or source acquisition. Serve `build/` with any static HTTP server.
- `make serve` serves `site/` locally on port 8731.

These checks validate the included publication, rather than rederiving blockchain histories. The full `scripts/pipeline.py check` also needs `data/raw/`, `data/timelines/`, source manifests and the original label lookup. Those files are intentionally outside the public snapshot. It can fail on a clean public clone until the source cache has been reacquired.

## Source refresh and full checks

Set `ETHERSCAN_API_KEY` in the process environment for refresh. Never save a key in source files, URLs, request indexes or logs. The exported collectors read the environment only. Public keyless routes cover other available sources. Etherscan requests stay within the free-tier limit; collectors cache requests and back off on provider errors.

```sh
.venv/bin/python -S -B scripts/pipeline.py refresh
.venv/bin/python -S -B scripts/pipeline.py check
```

Refresh collects the official ledger, issuer events, prices and address histories, then rebuilds analyses and site JSON. On a cold public clone, the exported pipeline first reacquires missing label-source inputs and restores the exact official-ledger snapshot used by supplemental label locators. That extra cache step is staged like other source acquisitions. It is resumable and bounded by source/step timeouts; recent successful source attempts have a cooldown. A missing raw-source cache bypasses that cooldown on a clean public clone. Use `--force` only when a new source pass is intended. `--max-age-hours`, `--network-timeout`, `--timeout` and `--workers` control freshness, deadlines and offline concurrency. A cold refresh can take hours, and third-party endpoints may no longer provide the original historical response. Refresh acquires the research lookup from its sources; exporting again applies the public label licence filter.

Every number is reproducible with the included scripts. `refresh` re-fetches source requests; `rebuild` replays available cached evidence. `export` rebuilds static JSON from those saved analyses and histories. Neither command substitutes unknown observations with zero. Before publishing changed data, review FINDINGS prose, source dates, coverage and prices. The numeric checker rejects stale finding annotations.

## Publication consistency

The pipeline stages changes in isolated generations and compares original signatures before replacing saved outputs. Conflicting concurrent changes are rejected. Evidence is published before analysis outputs; site metadata is published last. Multi-file publication can briefly expose a mixture of generations, so deploy a completed `build/` as one unit.

Process timeouts affect only subprocess groups created by that invocation. A pipeline lock prevents overlapping refreshes. Temporary generations are normally cleaned after success or failure. After a host crash, confirm the old run has stopped before removing its abandoned temporary generation.

## Evidence and release layout

Raw request/response envelopes occupy approximately 3 GB and are excluded, along with full normalized timelines and local SQLite indexes. `data/reference/raw_requests.jsonl.gz` records recoverable redacted requests for retained raw references. `raw_ref` values are source/request identities to re-fetch, rather than files in the public repo; fragments retain the original response locators. Re-fetching a request produces a new observation; it cannot guarantee the same historical payload. Generated analysis snapshots are calculation artifacts, not API requests; their producer scripts recreate them.

Third-party price series are omitted from the public export. `data/prices/manifest.csv` retains source URLs; `scripts/prices/price.py` fetches the series. USD values in `results/` were computed from these sources at their stated valuation times.

The release exporter keeps the seven compact result summaries, moves bulky pre-listing per-address detail to gzip, compresses small derived tables and excludes derived files whose compressed size exceeds 20 MB. `scripts/release/MANIFEST.json` records every publication file's size and SHA-256. `scripts/release/verify_public.py` checks it, so any intentional edit requires a fresh export.

Original input hashes remain provenance records. Publication metadata separately records the actual public result hashes after formatting, removal of process notes and removal of restricted nested label claims. Aggregate statistics retain their original classification scope. Full producer checks require regenerated original inputs; publication checks use the public files.
