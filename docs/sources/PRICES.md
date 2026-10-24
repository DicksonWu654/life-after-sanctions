# Price data

Refreshed **2026-10-23 UTC**. The latest complete daily date is **2026-10-22**; the latest hourly close is available at the **2026-10-23 08:00 UTC** boundary. The 22 requested assets have **78,430 daily observations** from each asset's first Coin Metrics Community `PriceUSD` date through 2026-10-22, with no missing UTC dates. Four hourly files contain **292,247 observations**.

The public export retains [`manifest.csv`](../../data/prices/manifest.csv) with source URLs and the fetch script. Third-party series stay in the local research cache; USD values in `results/` were computed from these sources at the stated valuation times. `scripts/pipeline.py refresh` re-fetches the source requests; `rebuild` replays the acquired cache. Raw captures are omitted for size and `raw_ref` values identify source requests to re-fetch. Locally, compressed series are in `data/prices/`. Each CSV row carries `source`, `source_url`, and `raw_ref`. Raw JSON API responses are gzip-compressed under [`data/raw/prices/`](../../data/raw/prices/); the matching `.request.json` file records the request URL, fetch time, HTTP status, and response hash. [`manifest.csv`](../../data/prices/manifest.csv) lists each file's first and last observation, count, and source. Refresh and full-date validation are implemented in [`price.py`](../../scripts/prices/price.py).

## Daily coverage

`first UTC date` is the first date in Coin Metrics' public daily `PriceUSD` catalog for the configured asset ID(s). Dates and counts below are reproduced by `price.py --check`; rows retain the underlying Coin Metrics asset ID in `source`.

| Asset | First UTC date | Daily rows | Source |
|---|---:|---:|---|
| BTC | 2010-07-18 | 5,941 | Coin Metrics `btc` (local series) |
| ETH | 2015-08-08 | 4,094 | Coin Metrics `eth` (local series) |
| USDT | 2014-10-06 | 4,400 | Coin Metrics `usdt` (local series) |
| USDC | 2018-09-28 | 2,947 | Coin Metrics `usdc` (local series) |
| TRX | 2018-06-25 | 3,042 | Coin Metrics `trx` (local series) |
| LTC | 2013-04-01 | 4,953 | Coin Metrics `ltc` (local series) |
| BCH | 2017-08-01 | 3,370 | Coin Metrics `bch` (local series) |
| BSV | 2018-11-15 | 2,899 | Coin Metrics `bsv` (local series) |
| DASH | 2014-02-08 | 4,640 | Coin Metrics `dash` (local series) |
| ZEC | 2016-10-29 | 3,646 | Coin Metrics `zec` (local series) |
| XMR | 2014-05-20 | 4,539 | Coin Metrics `xmr` (local series) |
| BTG | 2017-10-25 | 3,285 | Coin Metrics `btg`; Gate.io `BTG_USDT` for 2026-08-19–2026-10-22 (local series) |
| XVG | 2017-09-30 | 3,310 | Coin Metrics `xvg` (local series) |
| ETC | 2016-07-25 | 3,742 | Coin Metrics `etc` (local series) |
| XRP | 2014-08-15 | 4,452 | Coin Metrics `xrp` (local series) |
| BNB | 2017-07-15 | 3,387 | Coin Metrics `bnb` (local series) |
| SOL | 2020-04-10 | 2,387 | Coin Metrics `sol` (local series) |
| ARB | 2023-03-23 | 1,310 | Coin Metrics `arb` (local series) |
| MATIC/POL | 2019-06-22 | 2,680 | Coin Metrics `matic` plus `pol`; `pol` wins on overlapping dates (local series) |
| AVAX | 2020-09-23 | 2,221 | Coin Metrics `avax` (local series) |
| DOGE | 2014-01-23 | 4,656 | Coin Metrics `doge` (local series) |
| DAI | 2019-11-20 | 2,529 | Coin Metrics `dai` (local series) |

Coin Metrics stopped returning daily `btg` observations after 2026-08-18. Gate.io supplied the next 65 UTC daily closes through 2026-10-22. These are `BTG_USDT` closes and treat USDT as approximately USD. The saved Gate.io response is referenced by the BTG rows in `BTG_1d.csv.gz`.

MATIC/POL is one valuation series. Coin Metrics `matic` supplies the early history; `pol` (`POL (ex-MATIC)`) supplies rows from 2023-10-25 onward and takes precedence where both IDs overlap. The ticker change does not create a second asset series.

## Hourly coverage

| Asset | First hourly observation | Last hourly observation | Rows | Market/source |
|---|---|---|---:|---|
| BTC | 2018-01-01 01:00 UTC | 2026-10-23 08:00 UTC | 77,094 | Binance `BTCUSDT` (local series) |
| ETH | 2018-01-01 01:00 UTC | 2026-10-23 08:00 UTC | 77,094 | Binance `ETHUSDT` (local series) |
| TRX | 2018-06-11 12:00 UTC | 2026-10-23 08:00 UTC | 73,253 | Binance `TRXUSDT` (local series) |
| USDT | 2018-12-15 04:00 UTC | 2026-10-23 08:00 UTC | 64,806 | Binance `USDCUSDT`, close inverted (local series) |

Each hourly row is timestamped at the next UTC hour boundary, when its Binance candle close becomes available. For example, the 00:00–01:00 candle is timestamped 01:00 UTC. The three `*USDT` closes use the latest `USDCUSDT` close at or before that boundary to convert USDT to an estimated USD price. Before that market has data, the quote is treated as USD. USDT's own hourly price is the inverse of `USDCUSDT`, assuming USDC is USD. This gives hourly data beginning at the first available pair for each asset; it does not create USDT hourly observations for January–December 2018 before `USDCUSDT` began trading.

Binance returned no candle for some hours, so these files are observations rather than complete hourly grids. Between each file's first and last observations, BTC and ETH each have 27 gaps totaling 122 missing hours; TRX has 25 gaps totaling 88 hours; USDT has 21 gaps totaling 4,055 hours. Missing hours are not interpolated. `usd()` uses an hourly row only when its close boundary is within two hours of the requested time; otherwise it falls back to the daily series.

## Cross-check

The local `crosscheck.csv` contains ten seeded random UTC dates (seed `20261023`), comparing Coin Metrics daily `PriceUSD` with Binance's same-date UTC daily close for BTC, ETH, or TRX. Binance pairs are quoted in USDT, treated as USD for this check. Difference is `(Binance close − Coin Metrics PriceUSD) / Coin Metrics PriceUSD × 100`. The sample ranges from **−0.052392% to +0.192078%**.

| Asset | UTC date | Coin Metrics USD | Binance close, USDT≈USD | Difference | Raw references |
|---|---|---:|---:|---:|---|
| BTC | 2025-11-03 | 106,495.80279 | 106,583.04 | +0.081916% | local `crosscheck.csv` |
| ETH | 2026-02-03 | 2,231.42898305 | 2,233.72 | +0.102670% | local `crosscheck.csv` |
| BTC | 2026-02-23 | 64,689.9123308 | 64,656.02 | −0.052392% | local `crosscheck.csv` |
| ETH | 2026-03-01 | 1,938.46658767 | 1,939.71 | +0.064144% | local `crosscheck.csv` |
| ETH | 2026-03-07 | 1,970.38521596 | 1,969.59 | −0.040358% | local `crosscheck.csv` |
| ETH | 2026-04-21 | 2,323.70637347 | 2,327.14 | +0.147765% | local `crosscheck.csv` |
| TRX | 2026-04-28 | 0.32290834221 | 0.323 | +0.028385% | local `crosscheck.csv` |
| ETH | 2026-05-19 | 2,112.00750058 | 2,111.93 | −0.003670% | local `crosscheck.csv` |
| TRX | 2026-07-23 | 0.328569679521 | 0.3289 | +0.100533% | local `crosscheck.csv` |
| ETH | 2026-08-12 | 1,876.20622706 | 1,879.81 | +0.192078% | local `crosscheck.csv` |

These are same-date comparisons, not identical observation times: Coin Metrics rows retain the API's daily timestamp (00:00 UTC), while Binance closes at 23:59:59 UTC. This ten-date sample is a spot check, not a bound on differences for other dates or assets. For every table row, `crosscheck.csv` contains both raw response references; its corresponding `.request.json` files preserve the exact URLs.

## Provider findings and limits

| Provider | Use and observed limit |
|---|---|
| [Coin Metrics Community API v4](https://community-api.coinmetrics.io/v4/) | Primary daily source. Public `PriceUSD` at `frequency=1d` covered all 22 configured assets. It did not offer the requested 2018-onward `PriceUSD` hourly history. |
| [Binance Spot API v3](https://api.binance.com/api/v3/klines) | Hourly series for BTC, ETH, TRX, and the USDT/USDC conversion; also the ten daily cross-checks. |
| [Gate.io Spot API v4](https://www.gate.com/docs/developers/apiv4/en/) | BTG daily fallback for 2026-08-19 through 2026-10-22. The USDT quote is treated as USD. |
| [CoinGecko API v3](https://docs.coingecko.com/reference/coins-id-market-chart-range) | Checked the free historical range directly: an older-than-365-day request returned HTTP 401, error code `10012`, stating that public requests are limited to the past 365 days. The exact response is `data/raw/prices/coingecko/FREE-HISTORY-LIMIT/bb5169de19a430da0e284e2e04435c324f10406f22a7a347bcd00f80098a4ccc.json.gz`; `.request.json` records the URL. CoinGecko was not used in the final ten-date cross-check. |
| [CryptoCompare/CoinDesk API](https://developers.coindesk.com/) | The unauthenticated `histoday` request returned HTTP 401, `API key required`; not used. Saved response: `data/raw/prices/cryptocompare/HISTODAY-NO-KEY/213de85a398353692dd989f3240abe8bf2a50344c758b996bc18721ca0d03387.json.gz`, with the request in `.request.json`. |

Run `.venv/bin/python scripts/prices/price.py --probe-sources` to reproduce and archive the two access probes. The free CoinGecko history limit informed provider selection; current daily coverage is from Coin Metrics, plus the BTG Gate.io fallback.

## Lookup and contract extension

Call `usd(asset, ts_utc)` from `scripts/prices/price.py`; it returns `(price_usd, valuation_time_utc, source)`. It selects the latest stored observation at or before the requested UTC time, preferring an hourly row when it is no more than two hours old, otherwise daily (up to two days old). Naive timestamps are treated as UTC; an unknown asset or unavailable observation returns `(None, None, None)`. `MATIC`, `POL`, and `MATIC/POL` resolve to the combined series.

To add a supported ERC-20 or TRC-20 contract, run:

```sh
.venv/bin/python scripts/prices/price.py --add-contract TICKER ethereum CONTRACT_ADDRESS --start-date 2024-01-01
```

Use `tron` for a TRC-20 address. Replace the ticker, chain, address, and optional start date. The command stores the contract in `scripts/prices/contracts.json` and fetches a daily DefiLlama Coin Prices chart keyed by `chain:address`; availability depends on DefiLlama coverage for that contract. Raw chart responses are saved under `data/raw/prices/defillama/`, and the resulting CSV uses the same row-level source fields.

The registration and lookup path was exercised with the Ethereum USDC contract and the Tron USDT contract; the temporary aliases were removed after validation. The sample raw responses remain in `data/raw/prices/defillama/TESTUSDC-1D/6e64ca68b4b99610792cc3ca0a90f3540e887e7601ba914a0e925508298c8a5c.json.gz` and `data/raw/prices/defillama/TESTTRC-1D/054e5c27596fa4130e451cfe9709ccdbde4131f82f59cd66ee589785e285ab77.json.gz`; their `.request.json` files contain the exact chart URLs.
