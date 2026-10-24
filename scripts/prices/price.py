#!/usr/bin/env python3
"""Fetch, store, and look up UTC USD price observations.

The daily series use Coin Metrics Community API ``PriceUSD``.  Binance spot
klines supply the optional hourly series.  API response bodies are retained
as gzip JSON under data/raw/prices/ and each output row points back to them.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from bisect import bisect_right
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "prices"
RAW_DIR = ROOT / "data" / "raw" / "prices"
CONTRACTS_FILE = Path(__file__).resolve().parent / "contracts.json"
MANIFEST_FILE = PRICE_DIR / "manifest.csv"
CROSSCHECK_FILE = PRICE_DIR / "crosscheck.csv"
UTC = dt.timezone.utc
TODAY = dt.datetime.now(UTC).date()
DAILY_TARGET = TODAY - dt.timedelta(days=1)  # last complete UTC day
PAGE_SIZE = 10_000
BINANCE_LIMIT = 1_000
BINANCE_HOUR_MS = 3_600_000


ASSETS: list[dict[str, str]] = [
    {"symbol": "BTC", "cm": "btc", "cg": "bitcoin"},
    {"symbol": "ETH", "cm": "eth", "cg": "ethereum"},
    {"symbol": "USDT", "cm": "usdt", "cg": "tether"},
    {"symbol": "USDC", "cm": "usdc", "cg": "usd-coin"},
    {"symbol": "TRX", "cm": "trx", "cg": "tron"},
    {"symbol": "LTC", "cm": "ltc", "cg": "litecoin"},
    {"symbol": "BCH", "cm": "bch", "cg": "bitcoin-cash"},
    {"symbol": "BSV", "cm": "bsv", "cg": "bitcoin-sv"},
    {"symbol": "DASH", "cm": "dash", "cg": "dash"},
    {"symbol": "ZEC", "cm": "zec", "cg": "zcash"},
    {"symbol": "XMR", "cm": "xmr", "cg": "monero"},
    {"symbol": "BTG", "cm": "btg", "cg": "bitcoin-gold", "gate_pair": "BTG_USDT"},
    {"symbol": "XVG", "cm": "xvg", "cg": "verge"},
    {"symbol": "ETC", "cm": "etc", "cg": "ethereum-classic"},
    {"symbol": "XRP", "cm": "xrp", "cg": "ripple"},
    {"symbol": "BNB", "cm": "bnb", "cg": "binancecoin"},
    {"symbol": "SOL", "cm": "sol", "cg": "solana"},
    {"symbol": "ARB", "cm": "arb", "cg": "arbitrum"},
    {
        "symbol": "MATIC/POL",
        "cm": "matic",
        "cm_aliases": ["pol"],
        "cg": "polygon-ecosystem-token",
    },
    {"symbol": "AVAX", "cm": "avax", "cg": "avalanche-2"},
    {"symbol": "DOGE", "cm": "doge", "cg": "dogecoin"},
    {"symbol": "DAI", "cm": "dai", "cg": "dai"},
]

HOURLY_MARKETS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "TRX": "TRXUSDT",
}
STABLE_HOURLY_MARKET = "USDCUSDT"  # inverted to estimate USD per USDT

OUTPUT_FIELDS = [
    "asset",
    "frequency",
    "valuation_time_utc",
    "price_usd",
    "source",
    "source_url",
    "raw_ref",
]


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def slug(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", symbol.strip()).strip("-").upper()


def output_path(symbol: str, frequency: str) -> Path:
    return PRICE_DIR / f"{slug(symbol)}_{frequency}.csv.gz"


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def request_url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params)


def fetch_json(
    url: str,
    source: str,
    name: str,
    *,
    force: bool = False,
    retries: int = 5,
) -> tuple[Any, str]:
    """Fetch JSON and cache its gzip-compressed response with request metadata."""
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    source_dir = RAW_DIR / source / slug(name)
    path = source_dir / f"{key}.json.gz"
    metadata_path = source_dir / f"{key}.request.json"
    if path.exists() and not force:
        cached_status = 200
        if metadata_path.exists():
            try:
                cached_status = int(json.loads(metadata_path.read_text(encoding="utf-8")).get("http_status", 200))
            except (ValueError, json.JSONDecodeError):
                cached_status = 200
        if 200 <= cached_status < 300:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict) and ("error" in payload or "Err" in payload):
                raise RuntimeError(f"API error from {source}: {str(payload)[:500]} (saved {relative(path)})")
            return payload, relative(path)

    def save_body(body: bytes, status: int) -> None:
        source_dir.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("wb") as raw_fh:
            with gzip.GzipFile(fileobj=raw_fh, mode="wb", mtime=0) as zipped:
                zipped.write(body)
        temp_path.replace(path)
        metadata = {
            "request_url": url,
            "source": source,
            "fetched_at_utc": iso_utc(dt.datetime.now(UTC)),
            "http_status": status,
            "response_path": relative(path),
            "response_sha256": hashlib.sha256(body).hexdigest(),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    headers = {
        "User-Agent": "life-after-sanctions-price-pipeline/1.0",
        "Accept": "application/json",
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                body = response.read()
                status = response.status
            save_body(body, status)
            payload = json.loads(body)
            if isinstance(payload, dict) and ("error" in payload or "Err" in payload):
                raise RuntimeError(f"API error from {source}: {str(payload)[:500]} (saved {relative(path)})")
            return payload, relative(path)
        except urllib.error.HTTPError as exc:
            last_error = exc
            body = exc.read()
            save_body(body, exc.code)
            if exc.code not in (429, 500, 502, 503, 504):
                detail = body.decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"HTTP {exc.code} for {url}: {detail} (saved {relative(path)})") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if isinstance(exc, RuntimeError) and "API error" in str(exc):
                raise
        if attempt + 1 < retries:
            time.sleep(min(2**attempt, 16))
    raise RuntimeError(f"Failed request after {retries} attempts: {url}: {last_error}")


def saved_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with gzip.open(path, "rt", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["valuation_time_utc"]
            if row["frequency"] == "1d":
                key = key[:10]
            rows[key] = row
    return rows


def write_rows(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in sorted(rows, key=lambda item: item["valuation_time_utc"]):
        writer.writerow(row)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("wb") as raw_fh:
        with gzip.GzipFile(fileobj=raw_fh, mode="wb", mtime=0) as zipped:
            zipped.write(output.getvalue().encode("utf-8"))
    temp_path.replace(path)


def catalog_rows() -> tuple[dict[str, dict[str, Any]], str, str]:
    url = "https://community-api.coinmetrics.io/v4/catalog/assets"
    payload, raw_ref = fetch_json(url, "coinmetrics", "catalog", force=True)
    by_asset = {row.get("asset"): row for row in payload.get("data", [])}
    return by_asset, url, raw_ref


def cm_price_catalog(asset_id: str, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = catalog.get(asset_id)
    if not row:
        raise RuntimeError(f"Coin Metrics catalog has no asset id {asset_id}")
    metric = next((m for m in row.get("metrics", []) if m.get("metric") == "PriceUSD"), None)
    if not metric:
        raise RuntimeError(f"Coin Metrics has no PriceUSD metric for {asset_id}")
    frequency = next((f for f in metric.get("frequencies", []) if f.get("frequency") == "1d"), None)
    if not frequency or not frequency.get("community"):
        raise RuntimeError(f"Coin Metrics Community API has no daily PriceUSD for {asset_id}")
    return frequency


def coinmetrics_daily(
    asset: dict[str, str],
    catalog: dict[str, dict[str, Any]],
    *,
    full: bool,
) -> tuple[list[dict[str, str]], dict[str, Any], str]:
    target_path = output_path(asset["symbol"], "1d")
    existing = saved_rows(target_path)
    end = DAILY_TARGET.isoformat()
    merged = dict(existing)
    asset_ids = [asset["cm"], *asset.get("cm_aliases", [])]
    coverage_by_id = {asset_id: cm_price_catalog(asset_id, catalog) for asset_id in asset_ids}
    primary_url = ""
    for asset_id in asset_ids:
        coverage = coverage_by_id[asset_id]
        source_prefix = f"Coin Metrics Community API v4 PriceUSD ({asset_id}, 1d)"
        source_rows = [row for row in existing.values() if row["source"] == source_prefix]
        if full or not source_rows:
            start = coverage["min_time"][:10]
        else:
            latest = max(parse_time(row["valuation_time_utc"]) for row in source_rows)
            # Re-read a short overlap so refreshed or corrected recent records replace old ones.
            start = (latest.date() - dt.timedelta(days=2)).isoformat()
        url = request_url(
            "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
            {
                "assets": asset_id,
                "metrics": "PriceUSD",
                "frequency": "1d",
                "start_time": start,
                "end_time": end,
                "page_size": PAGE_SIZE,
            },
        )
        if not primary_url:
            primary_url = url
        next_url: str | None = url
        page = 0
        while next_url:
            payload, raw_ref = fetch_json(next_url, "coinmetrics", f"{asset['symbol']}-{asset_id}-1d-{page}")
            for index, record in enumerate(payload.get("data", []), start=1):
                value = record.get("PriceUSD")
                if value is None:
                    continue
                row = {
                    "asset": asset["symbol"],
                    "frequency": "1d",
                    "valuation_time_utc": iso_utc(parse_time(record["time"])),
                    "price_usd": str(value),
                    "source": source_prefix,
                    "source_url": next_url,
                    "raw_ref": f"{raw_ref}#row={index}",
                }
                # Alias assets are listed after the historical ticker and win
                # in the overlap once the new symbol is available.
                date_key = row["valuation_time_utc"][:10]
                prior = merged.get(date_key)
                prior_id = ""
                if prior and prior["source"].startswith("Coin Metrics"):
                    prior_id = prior["source"].split("(", 1)[1].split(",", 1)[0]
                prior_priority = asset_ids.index(prior_id) if prior_id in asset_ids else -1
                if prior is None or prior_id not in asset_ids or prior_priority <= asset_ids.index(asset_id):
                    merged[date_key] = row
            next_url = payload.get("next_page_url")
            page += 1
    coverage = min(coverage_by_id.values(), key=lambda item: item["min_time"])
    return list(merged.values()), coverage, primary_url


def coingecko_daily(asset: dict[str, str], *, force: bool = False) -> tuple[list[dict[str, str]], str, str]:
    coin_id = asset.get("cg")
    if not coin_id:
        raise RuntimeError(f"No CoinGecko id configured for {asset['symbol']}")
    url = request_url(
        f"https://api.coingecko.com/api/v3/coins/{urllib.parse.quote(coin_id, safe='')}/market_chart",
        {"vs_currency": "usd", "days": 365, "interval": "daily"},
    )
    payload, raw_ref = fetch_json(url, "coingecko", f"{asset['symbol']}-365d", force=force)
    if not isinstance(payload, dict) or not isinstance(payload.get("prices"), list):
        raise RuntimeError(f"Unexpected CoinGecko response for {asset['symbol']}")
    rows: list[dict[str, str]] = []
    for index, point in enumerate(payload["prices"], start=1):
        if len(point) < 2:
            continue
        observed = dt.datetime.fromtimestamp(float(point[0]) / 1000, UTC)
        if observed.date() > DAILY_TARGET:
            continue
        rows.append(
            {
                "asset": asset["symbol"],
                "frequency": "1d",
                "valuation_time_utc": iso_utc(observed),
                "price_usd": str(point[1]),
                "source": f"CoinGecko API v3 market_chart daily ({coin_id})",
                "source_url": url,
                "raw_ref": f"{raw_ref}#prices={index}",
            }
        )
    return rows, raw_ref, url


def gateio_daily_fill(asset: dict[str, str], missing_dates: list[str]) -> list[dict[str, str]]:
    """Fetch missing daily closes for an asset with a configured Gate.io pair."""
    pair = asset.get("gate_pair")
    if not pair or not missing_dates:
        return []
    first = dt.datetime.combine(dt.date.fromisoformat(min(missing_dates)), dt.time(), UTC)
    last_date = dt.date.fromisoformat(max(missing_dates))
    last = dt.datetime.combine(last_date, dt.time(23, 59, 59), UTC)
    url = request_url(
        "https://api.gateio.ws/api/v4/spot/candlesticks",
        {
            "currency_pair": pair,
            "interval": "1d",
            "from": int(first.timestamp()),
            "to": int(last.timestamp()),
            "limit": 1000,
        },
    )
    payload, raw_ref = fetch_json(url, "gateio", f"{asset['symbol']}-1d")
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Gate.io candlestick response for {pair}")
    missing_set = set(missing_dates)
    rows = []
    for index, candle in enumerate(payload, start=1):
        if len(candle) < 6:
            continue
        open_time = dt.datetime.fromtimestamp(int(candle[0]), UTC)
        day = open_time.date().isoformat()
        if day not in missing_set:
            continue
        close_time = dt.datetime.combine(open_time.date(), dt.time(23, 59, 59), UTC)
        rows.append(
            {
                "asset": asset["symbol"],
                "frequency": "1d",
                "valuation_time_utc": iso_utc(close_time),
                "price_usd": str(candle[5]),
                "source": f"Gate.io spot {pair} 1d close (USDT≈USD)",
                "source_url": url,
                "raw_ref": f"{raw_ref}#row={index}",
            }
        )
    return rows


def merge_daily(asset: dict[str, str], cm_rows: list[dict[str, str]], coverage: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    """Fill missing recent Coin Metrics dates with CoinGecko, preserving CM priority."""
    merged = {row["valuation_time_utc"][:10]: row for row in cm_rows}
    first = parse_time(coverage["min_time"]).date()
    expected = (DAILY_TARGET - first).days + 1
    missing = [
        (first + dt.timedelta(days=offset)).isoformat()
        for offset in range(max(0, expected))
        if (first + dt.timedelta(days=offset)).isoformat() not in merged
    ]
    if missing and (dt.date.fromisoformat(missing[-1]) >= TODAY - dt.timedelta(days=365)):
        try:
            for row in gateio_daily_fill(asset, missing):
                merged[row["valuation_time_utc"][:10]] = row
            missing = [day for day in missing if day not in merged]
        except Exception as exc:
            print(f"WARNING: Gate.io gap fill failed for {asset['symbol']}: {exc}", file=sys.stderr)
    if missing and (dt.date.fromisoformat(missing[-1]) >= TODAY - dt.timedelta(days=365)):
        try:
            cg_rows, _, _ = coingecko_daily(asset)
            for row in cg_rows:
                key = row["valuation_time_utc"][:10]
                if key in missing and key not in merged:
                    merged[key] = row
        except Exception as exc:
            print(f"WARNING: CoinGecko gap fill failed for {asset['symbol']}: {exc}", file=sys.stderr)
    return list(merged.values()), relative(output_path(asset["symbol"], "1d"))


def get_binance_klines(
    symbol: str,
    start_ms: int,
    end_ms: int,
    *,
    name: str,
) -> list[tuple[int, float, str, str]]:
    """Return (open_ms, close, raw_ref, request_url), retaining raw pages."""
    base = "https://api.binance.com/api/v3/klines"
    rows: list[tuple[int, float, str, str]] = []
    cursor = start_ms
    while cursor <= end_ms:
        url = request_url(
            base,
            {
                "symbol": symbol,
                "interval": "1h",
                "startTime": cursor,
                "endTime": end_ms,
                "limit": BINANCE_LIMIT,
            },
        )
        payload, raw_ref = fetch_json(url, "binance", f"{name}-1h")
        if isinstance(payload, dict):
            raise RuntimeError(f"Binance error for {symbol}: {payload}")
        if not payload:
            break
        last_open = cursor
        for index, kline in enumerate(payload, start=1):
            open_ms = int(kline[0])
            close_ms = int(kline[6])
            if close_ms > end_ms:
                continue
            rows.append((open_ms, float(kline[4]), f"{raw_ref}#row={index}", url))
            last_open = max(last_open, open_ms)
        next_cursor = last_open + BINANCE_HOUR_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        # Binance is public, but keep requests comfortably below its published limits.
        time.sleep(0.12)
    return rows


def binance_hourly(asset: dict[str, str], *, full: bool) -> list[dict[str, str]]:
    symbol = asset["symbol"]
    path = output_path(symbol, "1h")
    existing = saved_rows(path)
    start = dt.datetime(2018, 1, 1, tzinfo=UTC)
    if not full and existing:
        latest = max(parse_time(row["valuation_time_utc"]) for row in existing.values())
        # Stored times are candle-close boundaries, also the next candle's open.
        start = latest
    start_ms = int(start.timestamp() * 1000)
    current_hour = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    end_ms = int(current_hour.timestamp() * 1000) - 1

    market = HOURLY_MARKETS.get(symbol)
    fx_rows: list[tuple[int, float, str, str]] = []
    if symbol == "USDT":
        fx_path = output_path("USDT", "1h")
        fx_existing = saved_rows(fx_path)
        fx_start = dt.datetime(2018, 1, 1, tzinfo=UTC)
        if not full and fx_existing:
            latest_fx = max(parse_time(row["valuation_time_utc"]) for row in fx_existing.values())
            fx_start = latest_fx
        fx_rows = get_binance_klines(
            STABLE_HOURLY_MARKET,
            int(fx_start.timestamp() * 1000),
            end_ms,
            name="USDT-HOURLY-FX",
        )
    else:
        # The USDT file stores the inverse USDCUSDT close. Reconstruct the
        # quote rate from that row and retain its raw reference for each join.
        for row in saved_rows(output_path("USDT", "1h")).values():
            try:
                close = 1.0 / float(row["price_usd"])
                open_ms = int(parse_time(row["valuation_time_utc"]).timestamp() * 1000)
                fx_rows.append((open_ms, close, row["raw_ref"], row["source_url"]))
            except (ValueError, ZeroDivisionError):
                continue
    fx_by_time = {open_ms: (close, ref, url) for open_ms, close, ref, url in fx_rows}
    fx_times = sorted(fx_by_time)

    if symbol == "USDT":
        market_rows = []
    elif market:
        market_rows = get_binance_klines(market, start_ms, end_ms, name=symbol)
    else:
        return []

    fetched: dict[str, dict[str, str]] = {}
    if symbol == "USDT":
        for open_ms, close, raw_ref, url in fx_rows:
            if close <= 0:
                continue
            # A candle's close price becomes available at the next hour boundary.
            close_ms = open_ms + BINANCE_HOUR_MS
            observed = dt.datetime.fromtimestamp(close_ms / 1000, UTC)
            key = iso_utc(observed)
            fetched[key] = {
                "asset": symbol,
                "frequency": "1h",
                "valuation_time_utc": key,
                "price_usd": format(1.0 / close, ".12g"),
                "source": "Binance spot USDCUSDT 1h close inverted; USDC≈USD",
                "source_url": url,
                "raw_ref": raw_ref,
            }
    else:
        for open_ms, close, raw_ref, url in market_rows:
            # A candle's close price becomes available at the next hour boundary.
            close_ms = open_ms + BINANCE_HOUR_MS
            observed = dt.datetime.fromtimestamp(close_ms / 1000, UTC)
            key = iso_utc(observed)
            fx_index = bisect_right(fx_times, close_ms) - 1
            if fx_index >= 0:
                fx_close, fx_ref, fx_url = fx_by_time[fx_times[fx_index]]
                usd_per_usdt = 1.0 / fx_close if fx_close else 1.0
                assumption = "USDCUSDT inverted; USDC≈USD"
                refs = f"{raw_ref};{fx_ref}"
                urls = f"{url};{fx_url}"
            else:
                usd_per_usdt = 1.0
                assumption = "USDT treated as USD before USDCUSDT history"
                refs = raw_ref
                urls = url
            fetched[key] = {
                "asset": symbol,
                "frequency": "1h",
                "valuation_time_utc": key,
                "price_usd": format(close * usd_per_usdt, ".12g"),
                "source": f"Binance spot {market} 1h close ({assumption})",
                "source_url": urls,
                "raw_ref": refs,
            }

    merged = dict(existing)
    merged.update(fetched)
    return list(merged.values())


def load_contracts() -> list[dict[str, str]]:
    if not CONTRACTS_FILE.exists():
        return []
    try:
        payload = json.loads(CONTRACTS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid contracts config {CONTRACTS_FILE}: {exc}") from exc
    return payload.get("contracts", [])


def add_contract(symbol: str, chain: str, address: str, start_date: str | None) -> dict[str, str]:
    symbol = symbol.strip().upper()
    chain = chain.strip().lower()
    address = address.strip()
    if not re.fullmatch(r"[A-Z0-9._-]{2,24}", symbol):
        raise RuntimeError("Contract ticker must be 2–24 characters using A-Z, digits, dot, underscore, or hyphen")
    if not re.fullmatch(r"[a-z0-9_-]{2,32}", chain):
        raise RuntimeError("Chain should be a DefiLlama chain name such as ethereum, arbitrum, polygon, or tron")
    if chain in {"ethereum", "arbitrum", "base", "optimism", "polygon", "bsc", "avalanche"}:
        if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
            raise RuntimeError(f"{chain} contract must be a 0x address with 40 hexadecimal digits")
    elif chain == "tron":
        if not re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", address):
            raise RuntimeError("Tron contract must be a Base58 address beginning with T")
    elif not address:
        raise RuntimeError("Contract address cannot be empty")
    if start_date:
        dt.date.fromisoformat(start_date)
    asset = {
        "symbol": symbol,
        "contract_chain": chain,
        "contract_address": address,
        "contract_id": f"{chain}:{address}",
        "start_date": start_date or "",
    }
    all_assets = [a["symbol"].upper() for a in ASSETS] + [a["symbol"].upper() for a in load_contracts()]
    if symbol in all_assets:
        raise RuntimeError(f"Asset ticker already configured: {symbol}")
    contracts = load_contracts()
    contracts.append(asset)
    CONTRACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTRACTS_FILE.write_text(json.dumps({"contracts": contracts}, indent=2) + "\n", encoding="utf-8")
    return asset


def defillama_contract_daily(asset: dict[str, str], *, full: bool = True) -> list[dict[str, str]]:
    path = output_path(asset["symbol"], "1d")
    existing = saved_rows(path)
    if full or not existing:
        start = dt.date.fromisoformat(asset.get("start_date") or "2010-01-01")
    else:
        latest = max(parse_time(row["valuation_time_utc"]) for row in existing.values())
        start = latest.date() - dt.timedelta(days=2)
    start_dt = dt.datetime.combine(start, dt.time(), UTC)
    start_sec = int(start_dt.timestamp())
    span = (DAILY_TARGET - start).days + 1
    if span <= 0:
        return []
    coin = asset["contract_id"]
    url = request_url(
        f"https://coins.llama.fi/chart/{urllib.parse.quote(coin, safe=':')}",
        {"start": start_sec, "span": span, "period": "1d"},
    )
    payload, raw_ref = fetch_json(url, "defillama", f"{asset['symbol']}-1d", force=True)
    coin_data = payload.get("coins", {}).get(coin, {})
    rows = []
    for index, point in enumerate(coin_data.get("prices", []), start=1):
        observed = dt.datetime.fromtimestamp(float(point["timestamp"]), UTC)
        if observed.date() > DAILY_TARGET:
            continue
        rows.append(
            {
                "asset": asset["symbol"],
                "frequency": "1d",
                "valuation_time_utc": iso_utc(observed),
                "price_usd": str(point["price"]),
                "source": f"DefiLlama Coin Prices chart ({coin})",
                "source_url": url,
                "raw_ref": f"{raw_ref}#prices={index}",
            }
        )
    if not rows:
        raise RuntimeError(f"DefiLlama returned no chart prices for {coin}; verify token coverage")
    return rows


def save_manifest() -> None:
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    all_assets = ASSETS + load_contracts()
    for asset in all_assets:
        for frequency in ("1d", "1h"):
            path = output_path(asset["symbol"], frequency)
            if not path.exists():
                continue
            data = list(saved_rows(path).values())
            if not data:
                continue
            times = sorted(row["valuation_time_utc"] for row in data)
            sources = sorted({row["source"] for row in data})
            rows.append(
                {
                    "asset": asset["symbol"],
                    "frequency": frequency,
                    "file": relative(path),
                    "first_valuation_time_utc": times[0],
                    "last_valuation_time_utc": times[-1],
                    "observations": str(len(data)),
                    "source": " | ".join(sources),
                    "source_url": data[0]["source_url"],
                    "raw_ref": data[0]["raw_ref"],
                }
            )
    with MANIFEST_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "asset",
                "frequency",
                "file",
                "first_valuation_time_utc",
                "last_valuation_time_utc",
                "observations",
                "source",
                "source_url",
                "raw_ref",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def refresh(*, hourly: bool = True) -> None:
    catalog, catalog_url, catalog_ref = catalog_rows()
    print(f"Coin Metrics catalog saved: {catalog_ref}")
    for asset in ASSETS:
        print(f"daily {asset['symbol']}: fetching Coin Metrics PriceUSD", flush=True)
        path = output_path(asset["symbol"], "1d")
        full = not path.exists()
        cm_rows, coverage, _ = coinmetrics_daily(asset, catalog, full=full)
        daily_rows, _ = merge_daily(asset, cm_rows, coverage)
        write_rows(path, daily_rows)
    if hourly:
        # Fetch the USDT/USDC hourly FX stream first; the three quoted markets
        # then use the same stream rather than downloading it repeatedly.
        for symbol in ("USDT", "BTC", "ETH", "TRX"):
            asset = next(item for item in ASSETS if item["symbol"] == symbol)
            print(f"hourly {symbol}: fetching Binance klines", flush=True)
            rows = binance_hourly(asset, full=not output_path(symbol, "1h").exists())
            if rows:
                write_rows(output_path(symbol, "1h"), rows)
    for asset in load_contracts():
        print(f"daily {asset['symbol']}: fetching DefiLlama contract chart", flush=True)
        path = output_path(asset["symbol"], "1d")
        rows = defillama_contract_daily(asset, full=not path.exists())
        merged = saved_rows(path)
        for row in rows:
            merged[row["valuation_time_utc"][:10]] = row
        write_rows(path, merged.values())
    save_manifest()


def parse_daily_csv(asset: str) -> list[dict[str, str]]:
    path = output_path(asset, "1d")
    if not path.exists():
        return []
    return list(saved_rows(path).values())


def parse_hourly_csv(asset: str) -> list[dict[str, str]]:
    path = output_path(asset, "1h")
    if not path.exists():
        return []
    return list(saved_rows(path).values())


def resolve_asset(asset: str) -> dict[str, str] | None:
    normalized = asset.strip().upper()
    for item in ASSETS + load_contracts():
        symbol = item["symbol"].upper()
        if normalized == symbol or (symbol == "MATIC/POL" and normalized in {"MATIC", "POL"}):
            return item
        if item.get("contract_id", "").upper() == normalized:
            return item
    return None


_PRICE_CACHE: dict[str, tuple[float, list[str], list[dict[str, str]]]] = {}


def _lookup_rows(asset_symbol: str, frequency: str, timestamp: dt.datetime) -> dict[str, str] | None:
    path = output_path(asset_symbol, frequency)
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    cache_key = f"{asset_symbol}:{frequency}"
    cached = _PRICE_CACHE.get(cache_key)
    if cached is None or cached[0] != mtime:
        rows = list(saved_rows(path).values())
        rows.sort(key=lambda row: row["valuation_time_utc"])
        times = [row["valuation_time_utc"] for row in rows]
        _PRICE_CACHE[cache_key] = (mtime, times, rows)
        cached = _PRICE_CACHE[cache_key]
    _, times, rows = cached
    key = iso_utc(timestamp)
    index = bisect_right(times, key) - 1
    return rows[index] if index >= 0 else None


def usd(asset: str, ts_utc: str | dt.datetime) -> tuple[float | None, str | None, str | None]:
    """Return (USD price, observation time, source) at or before ``ts_utc``.

    Hourly observations are timestamped at the next UTC hour boundary, when a
    Binance candle close becomes available. They are used when no more than two
    hours old; otherwise the daily UTC series is used. Naive timestamps are
    treated as UTC. ``None`` values mean no stored observation exists at or
    before the requested time.
    """
    resolved = resolve_asset(asset)
    if not resolved:
        return None, None, None
    symbol = resolved["symbol"]
    timestamp = parse_time(ts_utc)
    hourly = _lookup_rows(symbol, "1h", timestamp)
    if hourly:
        age = timestamp - parse_time(hourly["valuation_time_utc"])
        if dt.timedelta(0) <= age <= dt.timedelta(hours=2):
            return float(hourly["price_usd"]), hourly["valuation_time_utc"], hourly["source"]
    daily = _lookup_rows(symbol, "1d", timestamp)
    if daily:
        age = timestamp - parse_time(daily["valuation_time_utc"])
        if dt.timedelta(0) <= age <= dt.timedelta(days=2):
            return float(daily["price_usd"]), daily["valuation_time_utc"], daily["source"]
    return None, None, None


def daily_gaps(asset: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> list[str]:
    if asset.get("cm"):
        coverages = [cm_price_catalog(asset_id, catalog) for asset_id in [asset["cm"], *asset.get("cm_aliases", [])]]
        first = min(parse_time(coverage["min_time"]).date() for coverage in coverages)
    else:
        if asset.get("start_date"):
            first = dt.date.fromisoformat(asset["start_date"])
        else:
            rows = parse_daily_csv(asset["symbol"])
            if not rows:
                return ["no-data"]
            first = min(dt.date.fromisoformat(row["valuation_time_utc"][:10]) for row in rows)
    rows = parse_daily_csv(asset["symbol"])
    present = {row["valuation_time_utc"][:10] for row in rows}
    expected_days = (DAILY_TARGET - first).days + 1
    return [
        (first + dt.timedelta(days=offset)).isoformat()
        for offset in range(max(0, expected_days))
        if (first + dt.timedelta(days=offset)).isoformat() not in present
    ]


def check_coverage() -> int:
    catalog, _, _ = catalog_rows()
    failures = 0
    for asset in ASSETS + load_contracts():
        try:
            gaps = daily_gaps(asset, catalog)
            rows = parse_daily_csv(asset["symbol"])
            if gaps:
                failures += len(gaps)
                preview = ", ".join(gaps[:8])
                print(f"GAP {asset['symbol']}: {len(gaps)} missing UTC dates; first: {preview}")
            else:
                first = min(r["valuation_time_utc"][:10] for r in rows) if rows else "missing"
                last = max(r["valuation_time_utc"][:10] for r in rows) if rows else "missing"
                print(f"OK {asset['symbol']}: {len(rows)} daily observations, {first} through {last}")
        except Exception as exc:
            failures += 1
            print(f"ERROR {asset['symbol']}: {exc}")
    if failures:
        print(f"Coverage check failed: {failures} date gaps/errors")
        return 1
    print("Coverage check passed for all configured assets through the last complete UTC day.")
    return 0


def cross_check(seed: int = 20261023, sample_size: int = 10) -> None:
    """Compare random daily observations with Binance UTC spot closes."""
    rng = random.Random(seed)
    start_day = DAILY_TARGET - dt.timedelta(days=364)
    day_count = (DAILY_TARGET - start_day).days + 1
    sample_days = sorted(rng.sample(range(day_count), sample_size))
    cross_assets = [asset for asset in ASSETS if asset["symbol"] in HOURLY_MARKETS]
    selected: list[dict[str, str]] = []
    daily_by_asset = {
        asset["symbol"]: {row["valuation_time_utc"][:10]: row for row in parse_daily_csv(asset["symbol"])}
        for asset in cross_assets
    }
    for offset in sample_days:
        day = (start_day + dt.timedelta(days=offset)).isoformat()
        asset = rng.choice(cross_assets)
        cm_row = daily_by_asset[asset["symbol"]].get(day)
        if not cm_row:
            raise RuntimeError(f"No Coin Metrics daily row for {asset['symbol']} on {day}")
        date_start = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(), UTC)
        start_ms = int(date_start.timestamp() * 1000)
        market = HOURLY_MARKETS[asset["symbol"]]
        url = request_url(
            "https://api.binance.com/api/v3/klines",
            {
                "symbol": market,
                "interval": "1d",
                "startTime": start_ms,
                "endTime": start_ms + 86_400_000 - 1,
                "limit": 1,
            },
        )
        payload, raw_ref = fetch_json(url, "binance", f"cross-{asset['symbol']}-{day}")
        if not payload:
            raise RuntimeError(f"Binance has no {market} daily candle for {day}")
        candle = payload[0]
        cm_price = float(cm_row["price_usd"])
        binance_price = float(candle[4])  # quote is USDT; treat as USD proxy
        difference = binance_price - cm_price
        percent = difference / cm_price * 100 if cm_price else 0.0
        selected.append(
            {
                "asset": asset["symbol"],
                "date_utc": day,
                "coinmetrics_price_usd": format(cm_price, ".12g"),
                "binance_close_usdt_usd_proxy": format(binance_price, ".12g"),
                "binance_valuation_time_utc": iso_utc(dt.datetime.fromtimestamp(int(candle[6]) / 1000, UTC)),
                "difference_usd": format(difference, ".12g"),
                "difference_percent": format(percent, ".6f"),
                "coinmetrics_raw_ref": cm_row["raw_ref"],
                "binance_raw_ref": f"{raw_ref}#row=1",
            }
        )
    if len(selected) != sample_size:
        raise RuntimeError(f"Could only produce {len(selected)} of {sample_size} cross-checks")
    CROSSCHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fields = list(selected[0].keys())
    with CROSSCHECK_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    print(f"Saved {len(selected)} random source comparisons to {relative(CROSSCHECK_FILE)}")


def probe_sources() -> None:
    """Archive keyless source-limit probes used in the source notes."""
    probes = [
        (
            "coingecko",
            "free-history-limit",
            request_url(
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart/range",
                {"vs_currency": "usd", "from": 1_500_000_000, "to": 1_500_500_000},
            ),
        ),
        (
            "cryptocompare",
            "histoday-no-key",
            request_url(
                "https://min-api.cryptocompare.com/data/v2/histoday",
                {"fsym": "BTC", "tsym": "USD", "limit": 1},
            ),
        ),
    ]
    for source, name, url in probes:
        try:
            payload, raw_ref = fetch_json(url, source, name, force=True)
            print(f"{source}: response archived at {raw_ref}; payload keys={list(payload)[:8]}")
        except Exception as exc:
            print(f"{source}: probe response archived; {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Incrementally fetch daily and available hourly prices")
    parser.add_argument("--cross-check", action="store_true", help="Compare 10 seeded random dates with Binance daily closes")
    parser.add_argument("--probe-sources", action="store_true", help="Archive responses checking free-source history access")
    parser.add_argument("--check", action="store_true", help="Check every configured daily UTC date for gaps")
    parser.add_argument(
        "--add-contract",
        nargs=3,
        metavar=("SYMBOL", "CHAIN", "ADDRESS"),
        help="Register an ERC-20/TRC-20 or other DefiLlama-supported contract and fetch its daily chart",
    )
    parser.add_argument("--start-date", help="Earliest date to request for --add-contract (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if args.add_contract:
        symbol, chain, address = args.add_contract
        asset = add_contract(symbol, chain, address, args.start_date)
        print(f"Registered {asset['symbol']} at {asset['contract_id']} in {relative(CONTRACTS_FILE)}")
        rows = defillama_contract_daily(asset)
        write_rows(output_path(asset["symbol"], "1d"), rows)
        save_manifest()
    if args.refresh:
        refresh()
    if args.cross_check:
        cross_check()
    if args.probe_sources:
        probe_sources()
    if args.check:
        return check_coverage()
    if not (args.refresh or args.cross_check or args.probe_sources or args.check or args.add_contract):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
