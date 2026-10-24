# Life After Sanctions

What happens to a cryptocurrency address after OFAC lists it? This research catalogues **1,148 historically listed chain–address pairs**, linked to **109 OFAC entity records** and **75 action dates**, across **18 mapped chains**, with observed histories where available. It combines official listing evidence, observed transfers and balances, stablecoin blacklist events, prices and public destination labels. **Data as of 2026-10-23; rerun `scripts/pipeline.py refresh` to update.**

[Explore the site](https://life-after-sanctions.shadow654.chatgpt.site/) · [Read the findings](FINDINGS.md) · [Source repository](https://github.com/DicksonWu654/life-after-sanctions)

- **474,308,691.68 USDT** at first freeze across six Tron addresses listed under BANK MARKAZI JOMHOURI ISLAMI IRAN. These are native token units measured on different freeze dates, rather than a simultaneous balance or USD valuation. [Evidence](FINDINGS.md#tether-froze-47430869168-usdt-across-bank-markazi-jomhouri-islami-irans-listed-tron-addresses)
- **341 of 341 historically listed Tron addresses** were blacklisted by Tether for USDT; **96** were blacklisted before their entire OFAC listing day began. [Evidence](FINDINGS.md#tether-blacklisted-all-341-ofac-listed-tron-addresses)
- **497 of 1,002 measured non-Tornado addresses** had an earlier qualifying outflow and no measured recognized-asset balance at the start of listing day. [Evidence](FINDINGS.md#497-listed-addresses-had-already-sent-funds-out-and-held-no-measured-balance-when-ofac-listed-them)
- Deposits into four classic Tornado Cash native-ETH pools rose **154.70%**, from **17,760.1 ETH** to **45,235.4 ETH**, in equal 30-day windows around delisting, excluding the delisting day. This is an observed association. [Evidence](FINDINGS.md#tornado-cashs-eth-deposits-rose-15470-after-ofac-removed-its-designation)

The [interactive site](https://life-after-sanctions.shadow654.chatgpt.site/) has case timelines, a program map, destination flows, freeze timing and an address explorer. Its launch address is configured in [release settings](scripts/release/config.py); the included site can also run locally.

## Reproduce

Python 3.11+ on Linux, `uv` and GNU Make are sufficient for the core pipeline. Core scripts use the Python standard library; no API key is needed to view or verify this snapshot.

```sh
uv venv .venv
uv pip install -r requirements.txt
make verify       # offline release checks against the included saved data
make build        # self-contained static build/ from the saved site export
make serve        # local site at http://127.0.0.1:8731
```

To collect newer source data, supply `ETHERSCAN_API_KEY` in the environment for refresh only, then run:

```sh
.venv/bin/python -S -B scripts/pipeline.py refresh
# After acquiring the full cache:
.venv/bin/python -S -B scripts/pipeline.py check
```

Refresh queries public providers, respects cached requests and rate limits, and rebuilds analyses and site data. It can take hours. Provider failures, retired networks and unavailable history remain coverage gaps. Review refreshed findings before publishing; this release installs no schedule. See [pipeline details](docs/PIPELINE.md).

Every number is reproducible by the included scripts. Raw API captures (approximately **3 GB**) and full normalized timelines are omitted for size. `scripts/pipeline.py refresh` re-fetches source requests; `scripts/pipeline.py rebuild` replays the acquired cache. Historical responses may have changed or become unavailable. `raw_ref` values identify sources and requests a reader can re-fetch, rather than files bundled in this repo. Recoverable requests are in the compressed [request index](data/reference/raw_requests.jsonl.gz) and the collectors. The release report records any references without recoverable request metadata. Public explorer/source links remain available. `make verify` checks the saved claim values and publication files; full producer arithmetic, historical pagination and raw transaction payload checks need the full raw cache and timelines. Per-address explorer rows link to public block explorers.

## Data

[Data dictionary and site contract](docs/DATA_CONTRACT.md) · [Definitions](docs/DEFINITIONS.md) · [Coverage by chain](docs/COVERAGE.md) · [Prior work](docs/PRIOR_ART.md)

| File | Unit / purpose |
|---|---|
| [ledger.csv](data/ledger.csv) | 1,185 address–entity rows, official identifiers and listing/removal evidence |
| [addresses.csv](data/addresses.csv) | 1,148 distinct chain–address pairs, including 14 marked untrackable |
| [actions.csv](data/actions.csv) | 75 official action-date records |
| [freezes.csv](data/freezes.csv) | 17,248 issuer blacklist, unblacklist and destruction event logs; broader than the OFAC-matched subset |
| [labels.csv.gz](data/labels/labels.csv.gz) | Redistributable exact-address source claims; labels are leads |
| `data/prices/manifest.csv`, `data/reference/`, `data/audit/`, `data/verify/` | Price-source manifest, references and independent checks |
| `results/`, `data/derived/`, `site/data/` | Analysis summaries, compressed detail and static publication data |

USD values in `results/` were computed from Coin Metrics, Binance and Gate-derived sources at the stated valuation times. The public export includes `data/prices/manifest.csv` with source URLs and `scripts/prices/price.py` to fetch the series; the third-party price series stay in the local research cache.

The label export preserves MIT, Apache-2.0 and official US-government factual sources. Sources without established redistribution permission and the Business Source License source are omitted from the label tables. The [label licence report](docs/LABELS.md) distinguishes the public subset from the original research lookup. Published aggregate research retains its stated original classification scope; omitted lookup records are not distributed through nested result claims.

## Interpretation

This is research, not legal or compliance advice. On-chain facts describe observed relationships, without accusing recipients of unlawful conduct; exchanges may have frozen or reported received funds. Name only what OFAC names. Public labels are leads, and unknown controllers remain unknown. “No outflow found” means within the data checked. Addresses, entities, actions, native coins and USD at a stated time are distinct units. Incomplete history, unknown tokens and prices, uncertain publication times, change outputs and limited labels constrain the conclusions.

Compiled with AI assistance; may contain errors; corrections welcome.

## Licence and citation

Code is **MIT**; original data and text are **CC BY 4.0**. Third-party material retains its own terms; see [LICENSE](LICENSE), [NOTICE](NOTICE), [label licences](data/labels/licenses/) and [vendored library notices](site/vendor/README.md).

> Life After Sanctions contributors. *Life After Sanctions*. Data snapshot: 2026-10-23. https://github.com/DicksonWu654/life-after-sanctions. CC BY 4.0 (original data and text).

Report corrections with a source URL and, where relevant, the chain, address, transaction hash and affected finding in [GitHub issues](https://github.com/DicksonWu654/life-after-sanctions/issues).
