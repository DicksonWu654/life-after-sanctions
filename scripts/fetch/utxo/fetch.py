#!/usr/bin/env python3
"""Evidence-preserving public UTXO history fetcher (Python standard library only).

See docs/sources/UTXO.md for amount/fee conventions and known source limitations.
No keys, project imports, executable remote content, or local chain downloads.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/utxo"
SYMBOLS = {"btc": "BTC", "ltc": "LTC", "bch": "BCH", "bsv": "BSV",
           "dash": "DASH", "zec": "ZEC", "btg": "BTG", "xvg": "XVG", "doge": "DOGE", "xmr": "XMR"}
ALIASES = {"xbt": "btc", "bitcoin": "btc", "litecoin": "ltc", "bitcoin-cash": "bch",
           "bitcoin_cash": "bch", "bitcoin-sv": "bsv", "bitcoin_sv": "bsv", "zcash": "zec",
           "bitcoin-gold": "btg", "bitcoin_gold": "btg", "verge": "xvg", "dogecoin": "doge", "monero": "xmr"}
BB = {"btc": "https://btc1.trezor.io/api/v2", "btg": "https://btgexplorer.com/api/v2"}
ESPLORA = {"btc": "https://mempool.space/api", "ltc": "https://litecoinspace.org/api"}
INSIGHT = {"dash": "https://insight.dash.org/insight-api"}
UA = "life-after-sanctions-research/1.0 (public historical address research)"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso(value):
    return dt.datetime.fromtimestamp(int(value), dt.timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def coins(n):
    return format(Decimal(n) / Decimal(100_000_000), ".8f")


def sat(n):
    return int(Decimal(str(n)) * 100_000_000)


def read_json(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{threading.get_ident()}.tmp")
    # C JSON encoding and one gzip write avoid millions of tiny Python writes
    # for large exchange/consolidation transactions.
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    with gzip.open(tmp, "wb", compresslevel=3) as f:
        f.write(payload)
    os.replace(tmp, path)


def cache_snapshot(snapshot, path):
    """Hard-link immutable response into its cache slot without duplicating disk."""
    tmp = path.with_name(path.name + f".{threading.get_ident()}.link.tmp")
    if tmp.exists():
        tmp.unlink()
    os.link(snapshot, tmp)
    os.replace(tmp, path)


def rel(path):
    return str(path.relative_to(ROOT))


class FetchError(RuntimeError):
    def __init__(self, message, raw_ref=None):
        super().__init__(message)
        self.raw_ref = raw_ref


class Client:
    def __init__(self, interval=1.1):
        self.interval = interval
        self.lock = threading.Lock()
        self.next_at = {}
        self.network_calls = 0
        self.request_log = []

    def get(self, url, *, fresh=False, timeout=40, retries=3):
        host = urllib.parse.urlsplit(url).netloc
        # Only public keyless endpoints are accepted; never persist credentials.
        if urllib.parse.urlsplit(url).username or re.search(r"(?i)(apikey|api_key|token|password)=", url):
            raise ValueError("Credential-bearing URL rejected")
        key = hashlib.sha256(url.encode()).hexdigest()
        path = RAW / host / key[:2] / (key + ".json.gz")
        if path.exists() and not fresh:
            cached = read_json(path)
            if cached.get("status") == 200:
                digest = hashlib.sha256(json.dumps(cached, sort_keys=True).encode()).hexdigest()[:16]
                snapshot = path.with_name(key + "-" + digest + ".json.gz")
                if not snapshot.exists():
                    write_json(snapshot, cached)
                return cached["response"], rel(snapshot) + "#response"
        last = None
        for attempt in range(retries):
            with self.lock:
                delay = max(0, self.next_at.get(host, 0) - time.monotonic())
                self.next_at[host] = time.monotonic() + delay + self.interval
                self.network_calls += 1
                self.request_log.append({"url": url, "attempt": attempt + 1})
            if delay:
                time.sleep(delay)
            status, headers = None, {}
            try:
                request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    status = response.status
                    headers = {k: response.headers[k] for k in ("ETag", "Last-Modified", "Retry-After") if k in response.headers}
                    body = response.read(100 * 1024 * 1024 + 1)
                    if len(body) > 100 * 1024 * 1024:
                        # Preserve oversized evidence without materializing a huge
                        # parsed object; the history caller can use smaller pages.
                        path.parent.mkdir(parents=True, exist_ok=True)
                        stamp = str(time.time_ns())
                        blob = path.with_name(key + '-' + stamp + '.body.json.gz')
                        tmp_blob = blob.with_name(blob.name + '.tmp')
                        total, digest, truncated = len(body), hashlib.sha256(body), False
                        with gzip.open(tmp_blob, 'wb', compresslevel=3) as output:
                            output.write(body)
                            while chunk := response.read(1024 * 1024):
                                output.write(chunk)
                                digest.update(chunk)
                                total += len(chunk)
                                if total > 512 * 1024 * 1024:
                                    truncated = True
                                    break
                        os.replace(tmp_blob, blob)
                        metadata = path.with_name(key + '-' + stamp + '.metadata.json.gz')
                        write_json(metadata, {'request': {'method': 'GET', 'url': url}, 'fetched_at': now(),
                                   'status': status, 'headers': headers, 'response': {'raw_ref': rel(blob)+'#',
                                   'uncompressed_bytes': total, 'sha256_uncompressed': digest.hexdigest(),
                                   'complete': not truncated, 'storage': 'unparsed gzip JSON body'}})
                        raise FetchError('API response exceeds 100 MiB parser cap; archived body: ' + rel(blob), rel(metadata)+'#response')
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = body.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                status = exc.code
                headers = {"Retry-After": exc.headers.get("Retry-After", "")}
                payload = exc.read(1024 * 1024).decode("utf-8", errors="replace")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                status = None
                payload = str(exc)
            envelope = {"request": {"method": "GET", "url": url}, "fetched_at": now(),
                        "status": status, "headers": headers, "response": payload}
            # Preserve every response snapshot. The stable key is also a cache pointer.
            snapshot = path.with_name(key + "-" + hashlib.sha256(json.dumps(envelope, sort_keys=True).encode()).hexdigest()[:16] + ".json.gz")
            write_json(snapshot, envelope)
            cache_snapshot(snapshot, path)
            ref = rel(snapshot) + "#response"
            if status == 200:
                return payload, ref
            last = FetchError(f"GET {url}: HTTP {status}; {str(payload)[:180]}", ref)
            if status is not None and status not in (429, 500, 502, 503, 504, 520, 524):
                break
            if attempt + 1 < retries:
                retry = headers.get("Retry-After", "")
                backoff = min(int(retry) if retry.isdigit() else 2 ** (attempt + 1), 30)
                if status == 429:
                    backoff = max(backoff, 30)
                with self.lock:
                    self.next_at[host] = max(self.next_at.get(host, 0), time.monotonic() + backoff)
                time.sleep(backoff)
        raise last


def bootstrap(client):
    base = "https://api.github.com/repos/0xB10C/ofac-sanctioned-digital-currency-addresses"
    commit, cref = client.get(base + "/commits/lists")
    sha = commit["sha"]
    tree, tref = client.get(base + "/git/trees/" + sha + "?recursive=1")
    rows, lists = [], []
    for item in tree["tree"]:
        match = re.fullmatch(r"sanctioned_addresses_(\w+)\.txt", item["path"])
        if not match:
            continue
        ticker = match[1]
        chain = ALIASES.get(ticker.lower(), ticker.lower())
        if chain not in SYMBOLS:
            continue
        url = f"https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/{sha}/{item['path']}"
        body, ref = client.get(url)
        for address in str(body).splitlines():
            address = address.strip()
            if address and not address.startswith("#"):
                rows.append({"chain": chain, "address": address, "source_url": url, "raw_ref": ref})
        lists.append({"ticker": ticker, "source_url": url, "raw_ref": ref})
    path = ROOT / "data/bootstrap/fetch_utxo.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["chain", "address", "source_url", "raw_ref"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["chain"] != "btc", r["chain"], r["address"])))
    write_json(RAW / "bootstrap-manifest.json.gz", {"fetched_at": now(), "commit": sha,
               "commit_raw_ref": cref, "tree_raw_ref": tref, "lists": lists, "address_count": len(rows)})
    return path


def load_addresses(path, chains=None):
    rows = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            chain = ALIASES.get(row["chain"].lower(), row["chain"].lower())
            if chain not in SYMBOLS or (chains and chain not in chains):
                continue
            address = row.get("address_normalized") or row.get("address")
            if not address or not re.fullmatch(r"[A-Za-z0-9:]+", address):
                raise ValueError(f"Invalid filename/address: {address!r}")
            rows[chain, address] = dict(row, chain=chain, address=address)
    return sorted(rows.values(), key=lambda r: (r["chain"] != "btc", r["chain"], r["address"]))


def normalize_tx(chain, address, tx, ref, style):
    inputs, outputs = [], []
    if style == "esplora":
        for v in tx["vin"]:
            prev = v.get("prevout") or {}
            inputs.append({"addresses": [prev["scriptpubkey_address"]] if prev.get("scriptpubkey_address") else [],
                           "value_sat": prev.get("value", 0), "txid": v.get("txid"), "vout": v.get("vout")})
        for v in tx["vout"]:
            outputs.append({"addresses": [v["scriptpubkey_address"]] if v.get("scriptpubkey_address") else [], "value_sat": v["value"]})
        block = tx.get("status", {}).get("block_height")
        timestamp = tx.get("status", {}).get("block_time")
        fee = tx.get("fee", 0)
    else:
        for v in tx.get("vin", []):
            addrs = v.get("addresses") or ([v["addr"]] if v.get("addr") else [])
            value = int(v.get("value", 0)) if style == "blockbook" else int(v.get("valueSat", sat(v.get("value", 0))))
            inputs.append({"addresses": addrs, "value_sat": value, "txid": v.get("txid"), "vout": v.get("vout")})
        for v in tx.get("vout", []):
            addrs = v.get("addresses") or v.get("scriptPubKey", {}).get("addresses", [])
            value = int(v.get("value", 0)) if style == "blockbook" else sat(v.get("value", 0))
            outputs.append({"addresses": addrs, "value_sat": value})
        block = tx.get("blockHeight", tx.get("blockheight", tx.get("block")))
        timestamp = tx.get("blockTime", tx.get("blocktime", tx.get("time")))
        fee = int(tx.get("fees", 0)) if style == "blockbook" else sat(tx.get("fees", 0))
        if style == "woc":
            # WhatsOnChain supplies prevout values/addresses under vin; if absent, resolve before normalization.
            fee = max(0, sum(v["value_sat"] for v in inputs) - sum(v["value_sat"] for v in outputs)) if inputs else 0
    own_in = sum(v["value_sat"] for v in inputs if address in v["addresses"])
    own_out = sum(v["value_sat"] for v in outputs if address in v["addresses"])
    delta = own_out - own_in
    all_in = sum(v["value_sat"] for v in inputs)
    # A joint-input transaction has no on-chain address-specific fee payer.
    # Pro rata is only an accounting convention, capped at this address's net debit.
    allocated_fee = min(max(-delta, 0), fee * own_in // all_in) if all_in else 0
    direction = "in" if delta >= 0 else "out"
    amount = abs(delta) - allocated_fee if delta < 0 else delta
    if own_in and own_out and amount == 0:
        direction = "self"
    in_addrs = sorted({a for v in inputs for a in v["addresses"]})
    out_addrs = sorted({a for v in outputs for a in v["addresses"]})
    return {"hash": tx.get("txid", tx.get("hash")), "block": block if isinstance(block, int) and block > 0 else None,
            "time_utc": iso(timestamp), "direction": direction, "asset": SYMBOLS[chain], "symbol": SYMBOLS[chain],
            "decimals": 8, "amount": coins(amount), "net_value": coins(delta), "net_value_sat": delta,
            "input_value": coins(own_in), "output_value": coins(own_out), "fee": coins(allocated_fee),
            "tx_fee": coins(fee), "fee_attribution": "pro_rata_input_value_capped_at_net_debit",
            "counterparties": sorted((set(in_addrs) | set(out_addrs)) - {address}),
            "input_addresses": in_addrs, "output_addresses": out_addrs, "inputs": inputs, "outputs": outputs,
            "raw_ref": ref}


def new_timeline(row, source):
    return {"schema_version": 1, "chain": row["chain"], "address": row["address"], "fetched_at": now(), "source": source,
            "coverage": {"from_block": None, "from_time": None, "to_block": None, "to_time": None,
                         "complete": False, "notes": []}, "txs": [], "balance_now": [],
            "amount_convention": "abs(net_value) excluding allocated fee on net debits; fee separately; self amount zero",
            "input_source_url": row.get("source_url"), "input_raw_ref": row.get("raw_ref")}


def finish(timeline, expected, balance, balance_ref, *, complete, notes, head=None, unconfirmed=0):
    timeline["fetched_at"] = now()
    txs = {t["hash"]: t for t in timeline["txs"]}
    timeline["txs"] = sorted(txs.values(), key=lambda t: (t.get("block") or 10 ** 12, t.get("time_utc") or "", t["hash"]))
    confirmed = [t for t in timeline["txs"] if t.get("block")]
    blocks = [t["block"] for t in confirmed]
    times = [t["time_utc"] for t in confirmed if t.get("time_utc")]
    observed = len(confirmed)
    if expected is not None and observed != expected:
        complete = False
        notes.append(f"Confirmed transaction count mismatch: API {expected}; saved unique {observed}.")
    delta = sum(t["net_value_sat"] for t in confirmed)
    if balance is not None and delta != balance:
        complete = False
        notes.append(f"History net delta {delta} sat versus reported confirmed balance {balance} sat; difference {delta-balance} sat.")
    balance_envelope = read_json(ROOT / balance_ref.split('#')[0]) if balance_ref else {}
    observed_at = balance_envelope.get('fetched_at', now())
    balance_source = balance_envelope.get('request', {}).get('url', timeline['source'])
    timeline["coverage"].update({"from_block": 0 if complete else (min(blocks) if blocks else None), "from_time": min(times) if times else None,
                                  "to_block": head, "to_time": observed_at,
                                  "complete": complete, "notes": list(dict.fromkeys(notes)),
                                  "expected_confirmed_txs": expected, "observed_confirmed_txs": observed,
                                  "oldest_saved_tx_time": min(times) if times else None,
                                  "latest_saved_tx_block": max(blocks) if blocks else None,
                                  "history_scope": "native transparent address history; API indexed confirmed transactions"})
    if balance is not None:
        timeline["balance_now"] = [{"asset": SYMBOLS[timeline["chain"]], "symbol": SYMBOLS[timeline["chain"]], "decimals": 8,
                                   "amount": coins(balance), "amount_sat": balance, "unconfirmed_amount": coins(unconfirmed),
                                   "reported_at": observed_at, "source": balance_source, "raw_ref": balance_ref}]
    timeline["validation"] = {"confirmed_net_sum_sat": delta, "reported_confirmed_balance_sat": balance,
                              "difference_sat": delta - balance if balance is not None else None,
                              "balance_matches": delta == balance if balance is not None else None}
    return timeline


def fetch_blockbook(client, row, old, refresh, max_pages, page_size):
    chain, address = row["chain"], row["address"]
    base = BB[chain]
    head, head_ref = client.get(f"{base}/address/{address}?details=basic", fresh=bool(old))
    expected, balance = int(head["txs"]), int(head["balance"])
    if old and old["coverage"].get("complete"):
        if expected == old["coverage"].get("expected_confirmed_txs") and balance == old["balance_now"][0]["amount_sat"] and not head.get('unconfirmedTxs') and all(t.get('block') for t in old['txs']):
            return finish(old, expected, balance, head_ref, complete=True, notes=old["coverage"]["notes"], unconfirmed=int(head.get("unconfirmedBalance", 0)))
        refresh = True
    timeline = new_timeline(row, base)
    query = ""
    incremental = bool(old and old["coverage"].get("complete") and refresh)
    if incremental:
        last = old["coverage"].get("latest_saved_tx_block") or 0
        start = max(0, last - 12)
        query = f"&from={start}"
        timeline["txs"] = [t for t in old["txs"] if t.get("block") and t["block"] < start]
    complete, notes, page = True, [], 1
    unconfirmed = int(head.get('unconfirmedBalance', 0))
    while True:
        if max_pages and page > max_pages:
            complete = False
            notes.append(f"Stopped at configured {max_pages} pages of {page_size}; older pages not fetched.")
            break
        data, ref = client.get(f"{base}/address/{address}?details=txs&pageSize={page_size}&page={page}{query}", fresh=incremental or (bool(old) and refresh))
        if page == 1:
            unconfirmed = int(data.get('unconfirmedBalance', unconfirmed))
        if "transactions" not in data and int(data.get("txs", 0)) > 0:
            raise FetchError("Blockbook omitted transaction bodies", ref)
        for i, tx in enumerate(data.get("transactions", [])):
            timeline["txs"].append(normalize_tx(chain, address, tx, ref + f".transactions[{i}]", "blockbook"))
        timeline["pagination"] = {"last_page": page, "total_pages": data.get("totalPages"), "page_size": page_size, "from_block": query}
        if page % 5 == 0:
            interim = finish(timeline, expected, balance, head_ref, complete=False, notes=["Pagination in progress; rerun resumes from request cache."])
            write_json(timeline_path(row), interim)
        if page >= int(data.get("totalPages", 1)):
            break
        page += 1
    return finish(timeline, expected, balance, head_ref, complete=complete, notes=notes,
                  unconfirmed=unconfirmed)


def fetch_esplora(client, row, old, refresh, max_pages):
    chain, address = row["chain"], row["address"]
    base = ESPLORA[chain]
    data, balance_ref = client.get(f"{base}/address/{address}", fresh=bool(old))
    stats = data["chain_stats"]
    expected = stats["tx_count"]
    balance = stats["funded_txo_sum"] - stats["spent_txo_sum"]
    mempool = data.get("mempool_stats", {})
    unconfirmed = mempool.get("funded_txo_sum", 0) - mempool.get("spent_txo_sum", 0)
    if old and old["coverage"].get("complete"):
        if expected == old["coverage"].get("expected_confirmed_txs") and balance == old["balance_now"][0]["amount_sat"] and not mempool.get('tx_count') and all(t.get('block') for t in old['txs']):
            return finish(old, expected, balance, balance_ref, complete=True, notes=old["coverage"]["notes"], unconfirmed=unconfirmed)
        refresh = True
    timeline = new_timeline(row, base)
    incremental = bool(old and old["coverage"].get("complete") and refresh)
    known = {t["hash"] for t in old["txs"] if t.get("block")} if incremental else set()
    if incremental:
        timeline["txs"] = [t for t in old["txs"] if t.get("block")]
    cursor, page, complete, notes = "", 0, True, []
    while expected:
        if max_pages and page >= max_pages:
            complete = False
            notes.append(f"Stopped at configured {max_pages} Esplora pages; older history not fetched.")
            break
        url = f"{base}/address/{address}/txs/chain" + (f"/{cursor}" if cursor else "")
        txs, ref = client.get(url, fresh=incremental or (bool(old) and not cursor))
        if not isinstance(txs, list):
            raise FetchError("Expected Esplora transaction array", ref)
        page += 1
        for i, tx in enumerate(txs):
            timeline["txs"].append(normalize_tx(chain, address, tx, ref + f"[{i}]", "esplora"))
        if page % 10 == 0:
            write_json(timeline_path(row), finish(timeline, expected, balance, balance_ref, complete=False, notes=["Pagination in progress; rerun resumes from request cache."]))
        if not txs or len(txs) < 25 or (incremental and any(t["txid"] in known for t in txs)):
            break
        new_cursor = txs[-1]["txid"]
        if new_cursor == cursor:
            raise FetchError("Esplora repeated pagination cursor", ref)
        cursor = new_cursor
    if unconfirmed or mempool.get("tx_count"):
        txs, ref = client.get(f"{base}/address/{address}/txs/mempool", fresh=True)
        for i, tx in enumerate(txs):
            timeline["txs"].append(normalize_tx(chain, address, tx, ref + f"[{i}]", "esplora"))
    return finish(timeline, expected, balance, balance_ref, complete=complete, notes=notes, unconfirmed=unconfirmed)


def fetch_insight(client, row, old, refresh):
    chain, address = row["chain"], row["address"]
    base = INSIGHT[chain]
    data, balance_ref = client.get(f"{base}/addr/{address}", fresh=bool(old))
    expected = data.get("txAppearances", data.get("txApperances"))
    balance = int(data["balanceSat"])
    timeline = new_timeline(row, base)
    known = {t["hash"]: t for t in old["txs"] if t.get("block")} if old else {}
    txids = data.get("transactions", [])
    notes = []
    for txid in txids:
        if txid in known:
            timeline["txs"].append(known[txid])
            continue
        tx, ref = client.get(f"{base}/tx/{txid}")
        timeline["txs"].append(normalize_tx(chain, address, tx, ref, "insight"))
    if len(txids) != expected:
        notes.append(f"Insight address list returned {len(txids)} txids for {expected} reported; pagination needed.")
    return finish(timeline, expected, balance, balance_ref, complete=len(txids) == expected, notes=notes,
                  unconfirmed=data.get("unconfirmedBalanceSat", 0))


def fetch_woc(client, row, old, refresh):
    address = row["address"]
    base = "https://api.whatsonchain.com/v1/bsv/main"
    balance_data, bref = client.get(f"{base}/address/{address}/balance", fresh=bool(old))
    history, href = client.get(f"{base}/address/{address}/history", fresh=bool(old))
    timeline = new_timeline(row, base)
    timeline["history_raw_ref"] = href
    known = {t["hash"]: t for t in old["txs"] if t.get("block")} if old else {}
    old_pending = {t['hash'] for t in old['txs'] if not t.get('block')} if old else set()
    for h in history:
        txid = h["tx_hash"]
        if txid in known:
            timeline["txs"].append(known[txid])
            continue
        tx, ref = client.get(f"{base}/tx/hash/{txid}", fresh=txid in old_pending)
        # Resolve all prevouts: WOC transaction bodies do not include their values.
        tx = json.loads(json.dumps(tx))
        prev_refs = []
        for vin in tx["vin"]:
            if vin.get("txid"):
                prev, pref = client.get(f"{base}/tx/hash/{vin['txid']}")
                v = next(v for v in prev["vout"] if v["n"] == vin["vout"])
                vin["valueSat"] = sat(v["value"])
                vin["addresses"] = v.get("scriptPubKey", {}).get("addresses", [])
                prev_refs.append(pref + f".vout[{vin['vout']}]")
        t = normalize_tx("bsv", address, tx, ref, "woc")
        t["prevout_raw_refs"] = prev_refs
        timeline["txs"].append(t)
    return finish(timeline, sum(h["height"] > 0 for h in history), int(balance_data["confirmed"]), bref,
                  complete=True, notes=["WhatsOnChain legacy history endpoint; completeness checked against current balance and returned tx list, not an independent index."],
                  unconfirmed=int(balance_data.get("unconfirmed", 0)))


def fetch_blockcypher(client, row, old, refresh):
    chain, address = row["chain"], row["address"]
    base = f"https://api.blockcypher.com/v1/{chain}/main"
    info, bref = client.get(f"{base}/addrs/{address}/balance", fresh=bool(old))
    expected, balance = info["n_tx"], info["balance"]
    if old and old["coverage"].get("complete"):
        if expected == old["coverage"].get("expected_confirmed_txs") and balance == old["balance_now"][0]["amount_sat"] and not info.get('unconfirmed_n_tx') and all(t.get('block') for t in old['txs']):
            return finish(old, expected, balance, bref, complete=True, notes=[], unconfirmed=info.get("unconfirmed_balance", 0))
        refresh = True
    timeline = new_timeline(row, base)
    incremental = bool(old and old["coverage"].get("complete") and refresh)
    query = ""
    if incremental:
        start = max(0, old["coverage"]["latest_saved_tx_block"] - 12)
        query = f"&after={start}"
        timeline["txs"] = [t for t in old["txs"] if t.get("block") and t["block"] <= start]
    before = None
    while expected:
        url = f"{base}/addrs/{address}/full?limit=50{query}" + (f"&before={before}" if before else "")
        data, ref = client.get(url, fresh=incremental)
        txs = data.get("txs", [])
        for i, tx in enumerate(txs):
            tref = ref + f".txs[{i}]"
            if len(tx["inputs"]) != tx["vin_sz"] or len(tx["outputs"]) != tx["vout_sz"]:
                tx, tref = client.get(f"{base}/txs/{tx['hash']}?limit=1000")
            if len(tx["inputs"]) != tx["vin_sz"] or len(tx["outputs"]) != tx["vout_sz"]:
                raise FetchError("BlockCypher truncated input/output arrays beyond 1000; missing prevout evidence", tref)
            transformed = {"txid": tx["hash"], "blockHeight": tx.get("block_height"), "fees": tx.get("fees", 0),
                           "blockTime": int(dt.datetime.fromisoformat(tx["confirmed"].replace("Z", "+00:00")).timestamp()) if tx.get("confirmed") else None,
                           "vin": [{"addresses": v.get("addresses", []), "value": v.get("output_value", 0), "txid": v.get("prev_hash"), "vout": v.get("output_index")} for v in tx["inputs"]],
                           "vout": [{"addresses": v.get("addresses", []), "value": v["value"]} for v in tx["outputs"]]}
            timeline["txs"].append(normalize_tx(chain, address, transformed, tref, "blockbook"))
        if not data.get("hasMore") or not txs:
            break
        blocks = [t["block_height"] for t in txs if t.get("block_height", 0) > 0]
        if not blocks or before == min(blocks):
            raise FetchError("BlockCypher block pagination cannot advance", ref)
        before = min(blocks)
    return finish(timeline, expected, balance, bref, complete=True, notes=[], unconfirmed=info.get("unconfirmed_balance", 0))


def source_gap(row, old):
    timeline = old or new_timeline(row, None)
    reasons = {"bch": "Trezor Blockbook returns HTTP 403; Blockchair reports HTTP 430 shared-IP quota block; loping.net serves a bot challenge, imaginary.cash times out. No usable history/balance source found.",
               "zec": "Transparent-address sources unavailable: Trezor Blockbook HTTP 403; zcha.in HTTP 520; other probes DNS, timeout or TLS failures. No usable history/balance source found. Shielded pool activity cannot be attributed to this transparent address.",
               "xvg": "Verge explorer endpoints fail DNS; verge-blockchain.info reports database reorg/maintenance HTTP 503; Cryptoid says hosting expired HTTP 404. No usable history/balance source found."}
    reasons['xmr'] = "Monero public addresses do not expose attributable transaction histories or balances: stealth outputs, confidential amounts and ring inputs prevent a public-address explorer reconstruction. No view key is available. Explicitly untrackable; balances and activity are unknown."
    timeline["coverage"]["notes"] = [reasons.get(row["chain"], "No working public keyless source configured."),
                                       "No absence-of-activity inference is supported. No designation-window or recent-90-day history has been fetched."]
    if row.get('untrackable_reason'):
        timeline['coverage']['notes'].append('Input ledger reason: ' + row['untrackable_reason'])
    timeline["source_probes"] = []
    if row['chain'] == 'xmr':
        timeline['privacy_source_url'] = 'https://www.getmonero.org/resources/moneropedia/stealthaddress.html'
        timeline['coverage']['untrackable'] = True
        privacy_manifest = RAW / 'privacy-sources.json.gz'
        if privacy_manifest.exists():
            timeline['source_probes'].extend(read_json(privacy_manifest)['sources'])
    for path in RAW.glob("*probes.json.gz"):
        for probe in read_json(path).get("probes", []):
            if probe["chain"] == row["chain"]:
                timeline["source_probes"].append({k: probe[k] for k in ("source_url", "raw_ref", "summary")})
    return timeline


def timeline_path(row):
    return ROOT / "data/timelines" / row["chain"] / (row["address"] + ".json.gz")


def fetch_one(client, row, args):
    path = timeline_path(row)
    old = read_json(path) if path.exists() else None
    if row['chain'] == 'btc':
        from electrum import bitcoin_address_error
        reason = bitcoin_address_error(row['address'])
        if reason:
            result = new_timeline(row, 'input_validation')
            result['coverage']['notes'] = [reason + '. No Bitcoin balance or history is asserted; explorer zero responses are not valid balance observations for this input.']
            ledger = ROOT / 'data/addresses.csv'
            if ledger.exists():
                with ledger.open(newline='') as handle:
                    for match in csv.DictReader(handle):
                        if (match.get('address_normalized') or match.get('address')) == row['address']:
                            result['chain_resolution'] = {'chain': match['chain'], 'source_url': match.get('source_url'), 'raw_ref': match.get('raw_ref')}
                            result['coverage']['notes'].append('The current OFAC-derived ledger resolves this input to ' + match['chain'] + '; use that chain fetcher. Original bootstrap ticker is preserved here as a coverage entry.')
            write_json(path, result)
            return row['chain'], row['address'], 0, False
    try:
        if row["chain"] in BB:
            try:
                result = fetch_blockbook(client, row, old, args.refresh, args.max_pages, args.page_size)
            except FetchError as exc:
                if row["chain"] not in ESPLORA:
                    raise
                print(f"fallback {row['chain']} {row['address']}: {exc}", flush=True)
                result = fetch_esplora(client, row, old, args.refresh, args.max_pages)
        elif row["chain"] in ESPLORA:
            result = fetch_esplora(client, row, old, args.refresh, args.max_pages)
        elif row["chain"] in INSIGHT:
            result = fetch_insight(client, row, old, args.refresh)
        elif row["chain"] == "bsv":
            result = fetch_woc(client, row, old, args.refresh)
        elif row["chain"] == "doge":
            result = fetch_blockcypher(client, row, old, args.refresh)
        elif row["chain"] == "bch":
            from electrum import fetch_bch
            result = fetch_bch(client, row, old, args.refresh)
        else:
            result = source_gap(row, old)
        write_json(path, result)
        return row["chain"], row["address"], len(result["txs"]), result["coverage"]["complete"]
    except Exception as exc:
        result = read_json(path) if path.exists() else (old or new_timeline(row, None))
        result["coverage"]["complete"] = False
        result["coverage"]["notes"].append(str(exc))
        if getattr(exc, "raw_ref", None):
            result.setdefault("error_raw_refs", []).append(exc.raw_ref)
        write_json(path, result)
        return row["chain"], row["address"], len(result["txs"]), "ERROR: " + str(exc)


def validate(rows):
    """Validate every saved timeline; use largest three and >=15 in the summary."""
    report = {"generated_at": now(), "script": "scripts/fetch/utxo/fetch.py --check", "addresses": [], "errors": []}
    for row in rows:
        path = timeline_path(row)
        if not path.exists():
            report["errors"].append(f"Missing timeline or coverage stub: {rel(path)}")
            continue
        obj = read_json(path)
        errs = []
        for key in ("chain", "address", "fetched_at", "source", "coverage", "txs", "balance_now"):
            if key not in obj:
                errs.append(f"Missing {key}")
        if not obj["coverage"]["complete"] and not obj["coverage"].get("notes"):
            errs.append("Incomplete timeline lacks reason")
        if row['chain'] == 'btc':
            from electrum import bitcoin_address_error
            if bitcoin_address_error(row['address']) and (obj['coverage']['complete'] or obj['balance_now'] or obj['txs']):
                errs.append('Invalid Bitcoin address has an asserted history or balance')
        confirmed = [t for t in obj["txs"] if t.get("block")]
        delta, accounting = 0, Decimal(0)
        hashes = set()
        for tx in obj["txs"]:
            for key in ("hash", "block", "time_utc", "direction", "asset", "symbol", "decimals", "amount", "counterparties", "fee", "raw_ref", "input_addresses", "output_addresses", "net_value"):
                if key not in tx:
                    errs.append(f"{tx.get('hash')}: missing {key}")
            if tx["hash"] in hashes:
                errs.append(f"Duplicate tx {tx['hash']}")
            hashes.add(tx["hash"])
            raw = ROOT / tx["raw_ref"].split("#")[0]
            if not raw.exists():
                errs.append(f"Missing raw {raw}")
            if tx.get("block"):
                delta += tx["net_value_sat"]
                accounting += (Decimal(tx["amount"]) if tx["direction"] == "in" else -Decimal(tx["amount"])) - Decimal(tx["fee"])
        balance = obj["balance_now"][0]["amount_sat"] if obj["balance_now"] else None
        if int(accounting * 100_000_000) != delta:
            errs.append("Flow-minus-fee accounting differs from input-output net delta")
        if obj["coverage"]["complete"] and delta != balance:
            errs.append("Complete history balance mismatch")
        item = {"chain": row["chain"], "address": row["address"], "timeline": rel(path), "complete": obj["coverage"]["complete"],
                "confirmed_txs": len(confirmed), "sum_net_sat": delta, "flow_minus_fee_sat": int(accounting * 100_000_000),
                "api_balance_sat": balance, "difference_sat": delta-balance if balance is not None else None, "errors": errs,
                "balance_raw_ref": obj["balance_now"][0]["raw_ref"] if obj["balance_now"] else None}
        item['raw_ref'] = item['balance_raw_ref'] or obj.get('input_raw_ref')
        item['source_url'] = obj['balance_now'][0]['source'] if obj['balance_now'] else obj.get('input_source_url')
        report["addresses"].append(item)
        report["errors"].extend(f"{row['chain']}:{row['address']}: {e}" for e in errs)
    eligible = sorted([r for r in report["addresses"] if r["api_balance_sat"] is not None], key=lambda r: -r["confirmed_txs"])
    report["largest_three"] = eligible[:3]
    report["validation_sample"] = eligible[:15]
    report["counts"] = {c: {"input_addresses": sum(r["chain"] == c for r in rows),
                               "timeline_files": sum(r["chain"] == c for r in report["addresses"]),
                               "complete": sum(r["chain"] == c and r["complete"] for r in report["addresses"]),
                               "confirmed_address_transactions": sum(r["confirmed_txs"] for r in report["addresses"] if r["chain"] == c)} for c in sorted({r["chain"] for r in rows})}
    write_json(RAW / "validation.json.gz", report)
    print(json.dumps({"counts": report["counts"], "validation_errors": len(report["errors"]), "validated_balances": len(eligible)}, indent=2))
    return len(report["errors"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--addresses", type=Path)
    p.add_argument("--bootstrap", action="store_true")
    p.add_argument("--chain", action="append")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--skip-complete", action="store_true", help="Resume interrupted batch; skip complete files without a head check")
    p.add_argument("--check", action="store_true", help="Offline schema, raw-reference, counts, and balance checks")
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--interval", type=float, default=1.1, help="Minimum seconds between requests per host")
    p.add_argument("--page-size", type=int, default=1000)
    p.add_argument("--max-pages", type=int, default=0, help="0 is unbounded; nonzero produces explicit incomplete coverage")
    args = p.parse_args()
    client = Client(args.interval)
    path = args.addresses
    if args.bootstrap:
        path = bootstrap(client)
    path = path or (ROOT / "data/addresses.csv" if (ROOT / "data/addresses.csv").exists() else ROOT / "data/bootstrap/fetch_utxo.csv")
    if not path.exists() and args.addresses is None:
        path = bootstrap(client)
    chains = {ALIASES.get(c.lower(), c.lower()) for c in args.chain} if args.chain else None
    rows = load_addresses(path, chains)
    if args.limit:
        rows = rows[:args.limit]
    if args.check:
        raise SystemExit(bool(validate(rows)))
    if args.skip_complete:
        rows = [row for row in rows if not timeline_path(row).exists() or not read_json(timeline_path(row))["coverage"].get("complete")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch_one, client, row, args) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            print(json.dumps(future.result()), flush=True)
    print(f"network_calls={client.network_calls}", flush=True)
    raise SystemExit(bool(validate(rows)))


if __name__ == "__main__":
    main()
