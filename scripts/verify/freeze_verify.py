#!/usr/bin/env python3
"""Independent issuer-freeze audit. Stdlib only; never imports analysis/freezes code.

Run: .venv/bin/python scripts/verify/freeze_verify.py [--check]
All HTTP responses are cached with request metadata under data/raw/verify_freeze/.
--check reads only these raw files and regenerates the CSV/report.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import html
import io
import json
import random
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/verify_freeze"
OUT = ROOT / "data/verify/freeze_verify.csv"
REPORT = ROOT / "docs/verify/FREEZE_VERIFY.md"
TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
RPC = "https://ethereum.publicnode.com"
CIRCLE_TOPIC = "0xffa4e6181777692565cf28528fc88fd1516ea86b56da075235fa575af6a4b855"  # keccak256 Blacklisted(address)
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
OFFLINE = False
LAST_CALL = {}


def rows(path):
    with (ROOT / path).open(newline="") as f:
        return list(csv.DictReader(f))


def b58_payload(address):
    n = 0
    for c in address:
        n = n * 58 + ALPHABET.index(c)
    b = n.to_bytes(25, "big")
    if b[0] != 0x41 or hashlib.sha256(hashlib.sha256(b[:21]).digest()).digest()[:4] != b[21:]:
        raise ValueError(f"bad Tron address {address}")
    return b[1:21]


def b58_address(payload):
    b = b"\x41" + payload
    q = b + hashlib.sha256(hashlib.sha256(b).digest()).digest()[:4]
    n = int.from_bytes(q, "big")
    chars = ""
    while n:
        n, rem = divmod(n, 58)
        chars = ALPHABET[rem] + chars
    return chars


def raw_request(url, method="GET", payload=None, kind="misc", minimum_interval=0.0):
    """Cache exact public requests; no API key is accepted or persisted."""
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode() if payload is not None else None
    ident = hashlib.sha256(method.encode() + b"\n" + url.encode() + b"\n" + (body or b"")).hexdigest()
    path = RAW / kind / (ident + ".json.gz")
    ref = str(path.relative_to(ROOT))
    if path.exists():
        with gzip.open(path, "rt") as f:
            return json.load(f)["response"], ref
    if OFFLINE:
        raise FileNotFoundError(ref)
    host = urllib.parse.urlsplit(url).netloc
    wait = minimum_interval - (time.monotonic() - LAST_CALL.get(host + kind, 0))
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, data=body, method=method,
        headers={"Content-Type": "application/json", "User-Agent": "freeze-verify/1.0"})
    for retry in range(6):
        try:
            LAST_CALL[host + kind] = time.monotonic()
            if url == RPC:
                proc = subprocess.run(["curl", "-fsS", "-m", "35", "-H",
                    "content-type: application/json", "--data-binary", "@-", url],
                    input=body or b"", capture_output=True, timeout=40)
                if proc.returncode:
                    raise RuntimeError(f"public RPC HTTP request failed: {proc.returncode}")
                blob = proc.stdout
            else:
                with urllib.request.urlopen(req, timeout=35) as r:
                    blob = r.read()
            try:
                result = json.loads(blob)
            except (ValueError, UnicodeDecodeError):
                result = blob.decode("utf-8", "replace")
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {"request": {"method": method, "url": url, "json": payload},
                      "fetched_at": dt.datetime.now(UTC).isoformat(), "response": result}
            with gzip.open(path, "wt") as f:
                json.dump(record, f, separators=(",", ":"))
            return result, ref
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or retry == 5:
                raise
            time.sleep(min(30, 2 ** retry + 2))
        except (TimeoutError, urllib.error.URLError):
            if retry == 5:
                raise
            time.sleep(min(30, 2 ** retry + 1))
    raise AssertionError("unreachable")


def tron_call(address, selector):
    arg = b58_payload(address).hex().rjust(64, "0")
    payload = {"owner_address": address, "contract_address": TRON,
        "function_selector": selector, "parameter": arg, "visible": True}
    obj, ref = raw_request("https://api.trongrid.io/wallet/triggerconstantcontract",
                           "POST", payload, "tron_constant", 0.28)
    values = obj.get("constant_result") or []
    if obj.get("result", {}).get("result") is not True or len(values) != 1:
        raise ValueError(f"failed Tron call {address} {selector}: {obj.get('result')}")
    return int(values[0], 16), ref


def now_block():
    obj, ref = raw_request("https://api.trongrid.io/wallet/getnowblock", kind="tron_block")
    header = obj["block_header"]["raw_data"]
    return header["number"], header["timestamp"], ref


def all_blacklist_events(cutoff_ms):
    params = urllib.parse.urlencode({"event_name": "AddedBlackList", "limit": 200,
        "only_confirmed": "true", "order_by": "block_timestamp,asc", "max_block_timestamp": cutoff_ms})
    url = f"https://api.trongrid.io/v1/contracts/{TRON}/events?{params}"
    found = defaultdict(list)
    page_refs = []
    seen = set()
    for page in range(300):
        if url in seen:
            raise ValueError("event pagination loop")
        seen.add(url)
        obj, ref = raw_request(url, kind="tron_events", minimum_interval=0.32)
        if obj.get("success") is not True:
            raise ValueError(f"Tron event query failed: {obj}")
        page_refs.append(ref)
        for ev in obj.get("data", []):
            if ev.get("event_name") != "AddedBlackList" or ev.get("contract_address") != TRON:
                continue
            raw_user = ev.get("result", {}).get("_user", "")
            try:
                user = b58_address(bytes.fromhex(raw_user.removeprefix("0x")[-40:]))
            except ValueError:
                continue
            found[user].append((ev, ref))
        next_url = obj.get("meta", {}).get("links", {}).get("next")
        if not next_url or not obj.get("data"):
            return found, page_refs, True
        url = next_url
    return found, page_refs, False


def transfer_balance(address, cutoff_ms):
    """Sum verified USDT Transfer events through the freeze timestamp.

    TronGrid omits block/log index here. A transfer in the freeze block is flagged.
    max_timestamp is inclusive; current balance reconciliation is separately reported.
    """
    params = urllib.parse.urlencode({"contract_address": TRON, "limit": 200,
        "only_confirmed": "true", "order_by": "block_timestamp,asc", "max_timestamp": cutoff_ms})
    url = f"https://api.trongrid.io/v1/accounts/{address}/transactions/trc20?{params}"
    seen_urls, refs = set(), []
    total = 0
    count = 0
    same_ts = 0
    for _ in range(300):
        if url in seen_urls:
            raise ValueError("transfer pagination loop")
        seen_urls.add(url)
        obj, ref = raw_request(url, kind="tron_transfers", minimum_interval=1.12)
        if obj.get("success") is not True:
            raise ValueError(f"Tron transfer query failed: {address}: {obj}")
        refs.append(ref)
        data = obj.get("data", [])
        for tx in data:
            if tx.get("token_info", {}).get("address") != TRON or tx.get("type") != "Transfer":
                continue
            # Keep all transfer rows. Two identical Transfer logs can occur in one
            # transaction; TronGrid does not expose their log indexes here.
            if int(tx["block_timestamp"]) > cutoff_ms:
                continue
            same_ts += int(tx["block_timestamp"] == cutoff_ms)
            val = int(tx["value"])
            if tx.get("to") == address:
                total += val
            if tx.get("from") == address:
                total -= val
            count += 1
        next_url = obj.get("meta", {}).get("links", {}).get("next")
        if not next_url or not data:
            return Decimal(total) / Decimal(10**6), count, same_ts, refs, True
        url = next_url
    return Decimal(total) / Decimal(10**6), count, same_ts, refs, False


def eth_call(address, block):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [
        {"to": USDC, "data": "0xfe575a87" + address[2:].rjust(64, "0")}, "latest"]}
    obj, ref = raw_request(RPC, "POST", payload, "eth_calls", 0.18)
    if "result" not in obj or not isinstance(obj["result"], str):
        raise ValueError(f"eth_call failed {address}: {obj}")
    return bool(int(obj["result"], 16)), ref


def eth_block():
    obj, ref = raw_request(RPC, "POST", {"jsonrpc": "2.0", "id": 1,
        "method": "eth_blockNumber", "params": []}, "eth_block")
    return int(obj["result"], 16), ref


def circle_events():
    """Read independent, paginated Blockscout Blacklisted logs, including timestamps."""
    base = ("https://eth.blockscout.com/api?" + urllib.parse.urlencode({
        "module": "logs", "action": "getLogs", "fromBlock": 0, "toBlock": "latest",
        "address": USDC, "topic0": CIRCLE_TOPIC, "offset": 1000}))
    events = defaultdict(list)
    refs = []
    for page in range(1, 100):
        obj, ref = raw_request(base + f"&page={page}", kind="circle_logs", minimum_interval=0.4)
        refs.append(ref)
        if obj.get("status") not in ("1", "0") or not isinstance(obj.get("result"), list):
            raise ValueError(f"Blockscout logs query failed: {str(obj)[:300]}")
        logs = obj["result"]
        for ev in logs:
            topics = ev.get("topics") or []
            if ev.get("address", "").lower() != USDC or len(topics) < 2 or topics[0] != CIRCLE_TOPIC or not topics[1]:
                continue
            address = "0x" + topics[1][-40:].lower()
            events[address].append((ev, ref))
        if len(logs) < 1000:
            return events, refs, True
    return events, refs, False


def action_page(url):
    obj, ref = raw_request(url, kind="ofac_actions")
    return obj if isinstance(obj, str) else json.dumps(obj), ref


def usdt_prices():
    url = ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?" +
           urllib.parse.urlencode({"assets": "usdt", "metrics": "PriceUSD", "frequency": "1d",
                                   "start_time": "2020-01-01", "end_time": "2026-10-23", "page_size": 10000}))
    obj, ref = raw_request(url, kind="prices")
    if "data" not in obj or obj.get("next_page_token"):
        raise ValueError("incomplete Coin Metrics USDT price series")
    return {r["time"][:10]: (Decimal(r["PriceUSD"]), r["time"]) for r in obj["data"]}, ref


def canonical_url(url):
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme, parts.netloc, parts.path,
            tuple(sorted(urllib.parse.parse_qsl(parts.query))))


def archived_transfer_balances(addresses, first_events):
    """Independently parse existing TronGrid HTTP captures, not derived timelines.

    The prior raw archive is read-only. A frozen manifest in our owned directory
    makes later offline checks immune to concurrent processes adding more captures.
    Repeated query windows are deduplicated by transfer attributes; an exact
    same-tx duplicate log cannot be distinguished because TronGrid omits logIndex.
    """
    manifest = RAW / "archive_manifest.json.gz"
    if manifest.exists():
        with gzip.open(manifest, "rt") as f:
            paths = json.load(f)["files"]
    else:
        if OFFLINE:
            raise FileNotFoundError(manifest)
        paths = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "data/raw/tron/trc20").glob("*.json.gz"))]
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(manifest, "wt") as f:
            json.dump({"files": paths, "source": "Saved TronGrid HTTP responses; paths only"}, f)
    totals = defaultdict(int)
    counts = defaultdict(int)
    same_ts = defaultdict(int)
    refs = defaultdict(set)
    seen_events = defaultdict(set)
    page_next = {}
    roots = defaultdict(list)
    for rel in paths:
        try:
            with gzip.open(ROOT / rel, "rt") as f:
                obj = json.load(f)
            url = obj["request"]["url"]
            parts = urllib.parse.urlsplit(url)
            address = parts.path.split("/accounts/")[1].split("/")[0]
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            continue
        if address not in addresses or address not in first_events:
            continue
        response = obj.get("response", {})
        if not isinstance(response, dict):
            continue
        params = urllib.parse.parse_qs(parts.query)
        key = canonical_url(url)
        next_url = response.get("meta", {}).get("links", {}).get("next")
        page_next[key] = canonical_url(next_url) if next_url else None
        if "fingerprint" not in params:
            roots[address].append((int(params.get("min_timestamp", ["0"])[0]),
                                   int(params.get("max_timestamp", ["9999999999999"])[0]), key))
        refs[address].add(rel)
        cutoff_ms = first_events[address]["block_timestamp"]
        for tx in response.get("data", []):
            if tx.get("type") != "Transfer" or tx.get("token_info", {}).get("address") != TRON:
                continue
            timestamp = int(tx["block_timestamp"])
            if timestamp > cutoff_ms:
                continue
            identity = (tx.get("transaction_id"), tx.get("from"), tx.get("to"), tx.get("value"), timestamp)
            if identity in seen_events[address]:
                continue
            seen_events[address].add(identity)
            amount = int(tx["value"])
            if tx.get("to") == address:
                totals[address] += amount
            if tx.get("from") == address:
                totals[address] -= amount
            counts[address] += 1
            same_ts[address] += timestamp == cutoff_ms
    result = {}
    for address in addresses:
        intervals = []
        for lower, upper, root in roots[address]:
            current, visited = root, set()
            while current is not None and current in page_next and current not in visited:
                visited.add(current)
                current = page_next[current]
            if current is None:
                intervals.append((lower, upper))
        intervals.sort()
        end = -1
        for lower, upper in intervals:
            if lower > end + 1:
                break
            end = max(end, upper)
        result[address] = {"balance": Decimal(totals[address]) / Decimal(10**6),
                           "count": counts[address], "same_ts": same_ts[address],
                           "refs": sorted(refs[address]),
                           "archive_coverage_verified": end >= first_events[address]["block_timestamp"]}
    return result, str(manifest.relative_to(ROOT))


def iso_ms(ms):
    return dt.datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace("+00:00", "Z")


def lag_hours(freeze_ms, date):
    noon = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(12), ET).astimezone(UTC)
    return (dt.datetime.fromtimestamp(freeze_ms / 1000, UTC) - noon).total_seconds() / 3600


def midnight_ms(date):
    return int(dt.datetime.combine(dt.date.fromisoformat(date), dt.time(), ET).astimezone(UTC).timestamp() * 1000)


def fmt(v, places=6):
    return f"{v:,.{places}f}"


def main():
    global OFFLINE
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="offline recompute from verify cache")
    args = ap.parse_args()
    OFFLINE = args.check
    ledger = rows("data/ledger.csv")
    addresses = rows("data/addresses.csv")
    ltrx = defaultdict(list)
    for r in ledger:
        if r["chain"] == "TRX":
            ltrx[r["address_normalized"]].append(r)
    atrx = {r["address_normalized"]: r for r in addresses if r["chain"] == "TRX"}
    aeth = {r["address_normalized"].lower(): r for r in addresses if r["chain"] == "ETH"}
    list_delta = sorted(set(ltrx) ^ set(atrx))
    date_delta = [(a, min(r["listed_date"] for r in ltrx[a]), atrx[a]["first_listed_date"])
                  for a in set(ltrx) & set(atrx)
                  if min(r["listed_date"] for r in ltrx[a]) != atrx[a]["first_listed_date"]]
    if list_delta or date_delta:
        print(f"Ledger/address disagreement: {list_delta[:5]} {date_delta[:5]}", file=sys.stderr)
    # Freeze the original claim's cohort and sampling frame. Concurrent processes can
    # refresh the mutable derived CSV while this audit is running.
    baseline_path = RAW / "claim_baseline.json.gz"
    with gzip.open(baseline_path, "rt") as f:
        candidate_rows = json.load(f)["rows"]
    baseline_ref = str(baseline_path.relative_to(ROOT))
    proposed = {r["address"]: r for r in candidate_rows
                if r["chain"] == "TRX" and r["issuer"] == "tether"}
    ranked = sorted(atrx, key=lambda a: Decimal(proposed.get(a, {}).get("balance_at_first_freeze_native") or "0"), reverse=True)
    top15 = ranked[:15]
    pre_candidates = [a for a in atrx if proposed.get(a, {}).get("lag_upper_hours") and
                      Decimal(proposed[a]["lag_upper_hours"]) < 0]
    pre_candidates.sort(key=lambda a: (atrx[a]["first_listed_date"], a))
    top10 = list(ranked[:10])
    pre10 = [a for a in pre_candidates if a not in top10][:10]
    sample = top10 + pre10
    remainder = [a for a in atrx if a not in sample]
    # Disperse the last 20 over designation dates rather than favoring a large batch.
    by_date = defaultdict(list)
    for a in remainder:
        by_date[atrx[a]["first_listed_date"]].append(a)
    rng = random.Random(20261023)
    for group in by_date.values():
        rng.shuffle(group)
    while len(sample) < 40 and any(by_date.values()):
        for date in sorted(by_date):
            if by_date[date] and len(sample) < 40:
                sample.append(by_date[date].pop())
    # The archive is reparsed independently for all 341. The proposed CSV only
    # defines which 334 addresses the published *known-balance* subtotal includes.
    balance_set = set(atrx)

    tron_block, tron_ms, tron_block_ref = now_block()
    events, event_refs, events_complete = all_blacklist_events(tron_ms)
    eth_height, eth_height_ref = eth_block()
    circle_logs, circle_refs, circle_complete = circle_events()
    prices, prices_ref = usdt_prices()
    verified = {}
    for n, a in enumerate(sorted(atrx), 1):
        status, status_ref = tron_call(a, "getBlackListStatus(address)")
        amount, amount_ref = tron_call(a, "balanceOf(address)")
        evs = sorted(events.get(a, []), key=lambda pair: (pair[0]["block_timestamp"], pair[0]["block_number"], pair[0]["transaction_id"]))
        first, event_ref = evs[0] if evs else (None, "")
        verified[a] = {"status": bool(status), "status_ref": status_ref,
            "current_usdt": Decimal(amount) / Decimal(10**6), "current_ref": amount_ref,
            "event": first, "event_ref": event_ref, "event_count": len(evs),
            "date": atrx[a]["first_listed_date"], "sample": a in sample,
            "top15": a in top15,
            "sample_stratum": "top10" if a in top10 else "definitely_pre10" if a in pre10 else "date_spread20" if a in sample else "extra_top15" if a in top15 else "population"}
        if n % 50 == 0:
            print(f"Tron contract calls {n}/{len(atrx)}", flush=True)

    # Event tx is queried separately, so sample confirmation does not rely solely
    # on contract-event pagination or any prior project extraction.
    for n, a in enumerate(sample, 1):
        item = verified[a]
        ev = item["event"]
        if ev:
            tx = ev["transaction_id"]
            obj, tx_ref = raw_request(f"https://api.trongrid.io/v1/transactions/{tx}/events",
                                      kind="tron_tx_events", minimum_interval=0.32)
            expected = "0x" + b58_payload(a).hex()
            item["tx_confirmed"] = any(e.get("event_name") == "AddedBlackList"
                and e.get("contract_address") == TRON
                and e.get("result", {}).get("_user", "").lower() == expected
                and e.get("block_timestamp") == ev["block_timestamp"] for e in obj.get("data", []))
            item["tx_ref"] = tx_ref
        if n % 10 == 0:
            print(f"Tron event tx checks {n}/{len(sample)}", flush=True)

    archive, archive_manifest_ref = archived_transfer_balances(atrx,
        {a: v["event"] for a, v in verified.items() if v["event"]})
    known_set = {a for a in atrx if proposed.get(a, {}).get("balance_at_first_freeze_native", "") != ""}
    for a in sorted(balance_set):
        item = verified[a]
        ev = item["event"]
        if not ev:
            continue
        record = archive[a]
        item.update(archive_balance_usdt=record["balance"],
                    archive_coverage_verified=record["archive_coverage_verified"],
                    transfer_count=record["count"],
                    same_timestamp_transfers=record["same_ts"],
                    transfer_refs=record["refs"],
                    claimed_known=a in known_set)
        if a in known_set:
            bal = record["balance"]
            item["freeze_usdt"] = bal
            price, observed = prices[iso_ms(ev["block_timestamp"])[:10]]
            item.update(price_usd=price, price_observed_utc=observed,
                        freeze_usd=bal * price, price_ref=prices_ref)
    # Freshly fetched history pages already in our cache independently
    # corroborate the archived captures. Never resume an incomplete page chain
    # here; the seven truly incomplete histories stay unknown.
    saved_offline = OFFLINE
    OFFLINE = True
    for a in sorted(balance_set):
        ev = verified[a]["event"]
        if not ev:
            continue
        try:
            bal, count, same_ts, refs, complete = transfer_balance(a, ev["block_timestamp"])
        except FileNotFoundError:
            continue
        if complete:
            verified[a].update(fresh_balance_usdt=bal, fresh_transfer_refs=refs,
                               fresh_history_complete=True,
                               fresh_archive_difference_usdt=bal - archive[a]["balance"])
    OFFLINE = saved_offline

    # Verify that the OFAC Recent Actions page for each sampled address both has
    # the action date in its URL and actually prints the address in its body.
    page_cache = {}
    for a in sample:
        item = verified[a]
        candidates = sorted((r for r in ltrx[a] if r["listed_date"] == item["date"]),
                            key=lambda r: r["listed_action_url"])
        url = candidates[0]["listed_action_url"] if candidates else ""
        item["action_url"] = url
        if url:
            if url not in page_cache:
                page_cache[url] = action_page(url)
            body, ref = page_cache[url]
            item["action_ref"] = ref
            item["action_address_found"] = a in html.unescape(body)
            item["action_url_date_match"] = item["date"].replace("-", "") in url

    # ETH circle sample: published ever-blacklisted rows select the stratified
    # group, and a public eth_call independently checks current contract state.
    eth_proposed = [r for r in candidate_rows
                    if r["chain"] == "ETH" and r["issuer"] == "circle" and
                       r["address"].lower() in aeth and len(r["address"]) == 42]
    eth_by_date = defaultdict(list)
    for r in eth_proposed:
        eth_by_date[aeth[r["address"].lower()]["first_listed_date"]].append(r["address"].lower())
    rng = random.Random(20261023)
    for group in eth_by_date.values():
        rng.shuffle(group)
    eth_sample = []
    while len(eth_sample) < 20 and any(eth_by_date.values()):
        for date in sorted(eth_by_date):
            if eth_by_date[date] and len(eth_sample) < 20:
                eth_sample.append(eth_by_date[date].pop())
    eth_results = {}
    for a in eth_sample:
        status, ref = eth_call(a, eth_height)
        eth_results[a] = (status, ref)

    columns = ["chain", "issuer", "address", "valid_token_address", "ofac_entity", "listed_date", "listed_action_url",
       "sample_group", "in_sample40", "sample_stratum", "ever_blacklisted", "current_blacklisted", "current_usdt",
       "first_freeze_utc", "first_freeze_block", "first_freeze_tx", "lag_hours_noon_et",
       "definitely_before_day", "freeze_balance_usdt", "freeze_balance_usd", "price_usd", "price_observed_utc", "claimed_known_balance_cohort", "partial_archive_balance_usdt", "balance_method", "transfer_count", "same_timestamp_transfers",
       "transfer_complete", "archive_coverage_verified", "fresh_history_complete", "fresh_balance_usdt", "fresh_archive_difference_usdt", "event_tx_confirmed", "ofac_page_address_found", "ofac_url_date_match",
       "source_url", "raw_ref", "status_raw_ref", "balance_raw_ref", "event_raw_ref",
       "event_tx_raw_ref", "transfer_raw_refs", "fresh_transfer_raw_refs", "archive_manifest_ref", "price_raw_ref", "ofac_raw_ref"]
    output = []
    for a in sorted(atrx):
        item = verified[a]
        ev = item["event"]
        lead = sorted(ltrx[a], key=lambda r: r["listed_date"])[0]
        row = {"chain": "TRX", "issuer": "Tether", "address": a, "valid_token_address": "true",
           "ofac_entity": lead["sdn_name"], "listed_date": item["date"],
           "listed_action_url": item.get("action_url") or lead["listed_action_url"],
           "sample_group": "top15" if item["top15"] else "stratified40" if item["sample"] else "population",
           "in_sample40": str(item["sample"]).lower(),
           "sample_stratum": item["sample_stratum"],
           "ever_blacklisted": str(bool(ev)).lower(), "current_blacklisted": str(item["status"]).lower(),
           "current_usdt": str(item["current_usdt"]), "first_freeze_utc": iso_ms(ev["block_timestamp"]) if ev else "",
           "first_freeze_block": ev["block_number"] if ev else "",
           "first_freeze_tx": ev["transaction_id"] if ev else "",
           "lag_hours_noon_et": f"{lag_hours(ev['block_timestamp'],item['date']):.6f}" if ev else "",
           "definitely_before_day": str(ev["block_timestamp"] < midnight_ms(item["date"])).lower() if ev else "",
           "freeze_balance_usdt": str(item.get("freeze_usdt", "")),
           "freeze_balance_usd": str(item.get("freeze_usd", "")),
           "price_usd": str(item.get("price_usd", "")),
           "price_observed_utc": item.get("price_observed_utc", ""),
           "claimed_known_balance_cohort": str(item.get("claimed_known", False)).lower(),
           "partial_archive_balance_usdt": str(item.get("archive_balance_usdt", "")),
           "balance_method": "reprocessed_saved_trongrid_responses" if item.get("claimed_known") else "unknown_incomplete_capture",
           "transfer_count": item.get("transfer_count", ""),
           "same_timestamp_transfers": item.get("same_timestamp_transfers", ""),
           "transfer_complete": str(bool(item.get("archive_coverage_verified") or item.get("fresh_history_complete"))).lower(),
           "archive_coverage_verified": str(item.get("archive_coverage_verified", False)).lower(),
           "fresh_history_complete": str(item.get("fresh_history_complete", False)).lower(),
           "fresh_balance_usdt": str(item.get("fresh_balance_usdt", "")),
           "fresh_archive_difference_usdt": str(item.get("fresh_archive_difference_usdt", "")),
           "event_tx_confirmed": str(item.get("tx_confirmed", "")).lower() if "tx_confirmed" in item else "",
           "ofac_page_address_found": str(item.get("action_address_found", "")).lower() if "action_address_found" in item else "",
           "ofac_url_date_match": str(item.get("action_url_date_match", "")).lower() if "action_url_date_match" in item else "",
           "source_url": f"https://tronscan.org/#/transaction/{ev['transaction_id']}" if ev else f"https://tronscan.org/#/address/{a}",
           "raw_ref": item["event_ref"] or item["status_ref"],
           "status_raw_ref": item["status_ref"], "balance_raw_ref": item["current_ref"],
           "event_raw_ref": item["event_ref"], "event_tx_raw_ref": item.get("tx_ref", ""),
           "transfer_raw_refs": ";".join(item.get("transfer_refs", [])),
           "fresh_transfer_raw_refs": ";".join(item.get("fresh_transfer_refs", [])),
           "archive_manifest_ref": archive_manifest_ref,
           "price_raw_ref": item.get("price_ref", ""), "ofac_raw_ref": item.get("action_ref", "")}
        output.append(row)
    circle_lags = []
    circle_matched = 0
    for a in sorted(aeth):
        status, status_ref = eth_results.get(a, (None, ""))
        valid = len(a) == 42 and a.startswith("0x") and all(c in "0123456789abcdef" for c in a[2:])
        matched_logs = sorted(circle_logs.get(a, []), key=lambda pair: (int(pair[0]["blockNumber"], 16), int(pair[0]["logIndex"], 16))) if valid else []
        ev, event_ref = matched_logs[0] if matched_logs else (None, "")
        if ev:
            circle_matched += 1
            circle_lags.append(lag_hours(int(ev["timeStamp"], 16) * 1000, aeth[a]["first_listed_date"]))
        lead = sorted((r for r in ledger if r["chain"] == "ETH" and r["address_normalized"].lower() == a),
                      key=lambda r: r["listed_date"])[0]
        output.append({"chain": "ETH", "issuer": "Circle", "address": a,
            "valid_token_address": str(valid).lower(),
            "ofac_entity": lead["sdn_name"], "listed_date": aeth[a]["first_listed_date"],
            "listed_action_url": lead["listed_action_url"], "sample_group": "circle20" if a in eth_results else "population",
            "ever_blacklisted": str(bool(ev)).lower(),
            "current_blacklisted": str(status).lower() if status is not None else "",
            "first_freeze_utc": iso_ms(int(ev["timeStamp"], 16) * 1000) if ev else "",
            "first_freeze_block": int(ev["blockNumber"], 16) if ev else "",
            "first_freeze_tx": ev["transactionHash"] if ev else "",
            "lag_hours_noon_et": f"{lag_hours(int(ev['timeStamp'],16)*1000,aeth[a]['first_listed_date']):.6f}" if ev else "",
            "definitely_before_day": str(int(ev["timeStamp"],16)*1000 < midnight_ms(aeth[a]["first_listed_date"])).lower() if ev else "",
            "source_url": f"https://eth.blockscout.com/tx/{ev['transactionHash']}" if ev else lead["listed_action_url"],
            "raw_ref": event_ref or lead["raw_ref"], "event_raw_ref": event_ref,
            "status_raw_ref": status_ref})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader(); writer.writerows(output)
    csv_text = csv_buffer.getvalue()
    if args.check:
        if not OUT.exists() or OUT.read_bytes() != csv_text.encode():
            raise AssertionError(f"offline result differs: {OUT}")
    else:
        OUT.write_text(csv_text)

    event_matched = sum(bool(v["event"]) for v in verified.values())
    current = sum(v["status"] for v in verified.values())
    current_positive = sum(v["current_usdt"] > 0 for v in verified.values())
    lags = [lag_hours(v["event"]["block_timestamp"], v["date"]) for v in verified.values() if v["event"]]
    pre = sum(v["event"]["block_timestamp"] < midnight_ms(v["date"]) for v in verified.values() if v["event"])
    far_pre = sum(v["event"]["block_timestamp"] < midnight_ms(v["date"]) - 30 * 86400000 for v in verified.values() if v["event"])
    top_sum = sum((verified[a].get("freeze_usdt", Decimal(0)) for a in top15), Decimal(0))
    full_sum = sum((v.get("freeze_usdt", Decimal(0)) for v in verified.values()), Decimal(0))
    full_usd = sum((v.get("freeze_usd", Decimal(0)) for v in verified.values()), Decimal(0))
    claim_total = Decimal("529064435.426376")
    claim_usd = Decimal("529155483.918")
    claim_top = sum((Decimal(proposed[a].get("balance_at_first_freeze_native") or "0") for a in top15), Decimal(0))
    top_diff = top_sum - claim_top
    confirmed_tx = sum(verified[a].get("tx_confirmed") is True for a in sample)
    action_found = sum(verified[a].get("action_address_found") is True for a in sample)
    complete_balances = sum(bool(verified[a].get("archive_coverage_verified") or verified[a].get("fresh_history_complete")) for a in known_set)
    archive_covered = sum(bool(verified[a].get("archive_coverage_verified")) for a in known_set)
    fresh_complete = sum(bool(v.get("fresh_history_complete")) for v in verified.values())
    fresh_agree = sum(bool(v.get("fresh_history_complete") and v.get("fresh_archive_difference_usdt") == 0) for v in verified.values())
    sample_covered = sum(bool(verified[a].get("archive_coverage_verified") or verified[a].get("fresh_history_complete")) for a in sample)
    top_covered = sum(bool(verified[a].get("archive_coverage_verified") or verified[a].get("fresh_history_complete")) for a in top15)
    unknown_addresses = sorted(set(atrx) - known_set)
    eth_agree = sum(eth_results[a][0] == (next(r for r in eth_proposed if r["address"].lower() == a)["blacklisted_current"] == "true") for a in eth_sample)
    action_issues = [a for a in sample if not verified[a].get("action_address_found") or not verified[a].get("action_url_date_match")]
    same_block_candidates = sum(v.get("same_timestamp_transfers", 0) > 0 for v in verified.values())
    lines = ["# Independent issuer-freeze verification", "",
        f"Run: `.venv/bin/python scripts/verify/freeze_verify.py --check` (offline). Raw HTTP responses: `data/raw/verify_freeze/`. Evidence rows: `data/verify/freeze_verify.csv` ({len(output)} rows).",
        "", "## Scope and results", "",
        f"Tron snapshot began at block **{tron_block:,}** ({iso_ms(tron_ms)}), raw `{tron_block_ref}`. Contract calls made for every address over a moving latest-block window, so the two current-state calls per address are not atomic. Ethereum's initial block-height reference was **{eth_height:,}**, raw `{eth_height_ref}`; the 20 eth_call requests used `latest` over a moving window because the public RPC restricts historical calls. T_pub is 12:00 America/New_York on the first address listing date.",
        "", "| Claim | Verdict | Independent result |", "|---|---|---|",
        f"| (a) Tether ever blacklisted all 341 OFAC Tron addresses | {'CONFIRMED' if event_matched == 341 and events_complete else 'ADJUSTED'} | {event_matched}/{len(atrx)} have a first AddedBlackList event in the complete contract event crawl; {current}/{len(atrx)} currently return true from getBlackListStatus. Current balanceOf is positive for {current_positive}/{len(atrx)} addresses. |",
        f"| (b) Median signed lag about −7.3 h; 96 definitely before listing day | {'CONFIRMED' if event_matched == 341 and abs(statistics.median(lags)+7.312)<0.05 and pre==96 else 'ADJUSTED'} | Median {statistics.median(lags):.3f} hours; {pre} events precede 00:00 ET on the first listing date. |",
        f"| (c) About 529M USDT held by all 341 at first freeze | ADJUSTED | Corrected wording: {fmt(full_sum)} USDT is the rederived **known-balance subtotal for {len(known_set)}/{len(atrx)} addresses**; {len(unknown_addresses)} first-freeze balances remain unknown, so there is no verified all-address total. Daily-price proxy valuation of the known subtotal: {fmt(full_usd,3)} USD across different freeze dates. |",
        f"| (d) Circle ever blacklisted 216/217 ETH identifiers; median 8.3 h | {'CONFIRMED' if circle_matched == 216 and circle_complete and abs(statistics.median(circle_lags)-8.310)<0.05 else 'ADJUSTED'} | {circle_matched}/{len(aeth)} have a Blacklisted event in the independent Blockscout contract-log crawl; median signed lag {statistics.median(circle_lags):.3f} hours. Public RPC eth_call at `latest` checked {len(eth_sample)} valid 0x identifiers ({eth_agree} agree with the proposed current state). The 217th ledger string has 39 hex digits and is invalid for ABI address calls. |",
        "", "## Denominators and method", "",
        f"`data/ledger.csv` independently contains {len(ltrx)} distinct TRX addresses; `data/addresses.csv` contains {len(atrx)}. Set differences: {len(list_delta)}; first-date differences: {len(date_delta)}. ETH inventory has {len(aeth)} distinct strings. No prior freeze code was imported. The original candidate ranking, prepublication stratum, and {len(known_set)}-address known-balance cohort were frozen in `{baseline_ref}` because a concurrent process refreshed the mutable derived CSV during this audit. That later refresh newly measured `TYq3iRujcBELXX89i9JY32UmLxcyZAJe7E`; this report tests the original 529,064,435.426376 USDT claim. No proposed event timestamp or amount was accepted as evidence.",
        "", f"The Tron contract event crawl saved {len(event_refs)} pages and {'reached its terminal page' if events_complete else 'hit the 300-page safety bound'}. First event is the earliest AddedBlackList by block time for each address. Circle Blacklisted logs came from {len(circle_refs)} Blockscout page(s), {'terminal page reached' if circle_complete else 'page limit reached'}, and were matched by the indexed address topic. The stratified sample has {len(sample)} unique Tron addresses: top 10 proposed balances, 10 other proposed definitely-prepublication cases, and 20 spread over OFAC action dates. Separate transaction event queries confirmed {confirmed_tx}/{len(sample)} first events. OFAC Recent Actions HTML printed the listed identifier in {action_found}/{len(sample)} pages; the URL date was separately checked in the CSV.",
        "", f"The verifier reparsed existing saved TronGrid HTTP responses listed in `{archive_manifest_ref}` to reconstruct balances; these source captures were collected by another job and were **not** treated as derived balances. It independently closed pagination and time-range coverage for {archive_covered}/{len(known_set)} claimed-known histories; fresh TronGrid histories closed for {fresh_complete} addresses and matched the archived result exactly for {fresh_agree}. Combined coverage checks close {complete_balances}/{len(known_set)} claimed-known histories, including {sample_covered}/{len(sample)} of the stratified sample and {top_covered}/{len(top15)} of the top 15. Remaining archived balances reproduce the source captures but their page continuity is not independently proven. {len(unknown_addresses)} addresses in the original claim cohort lack a defensible first-freeze amount; partial sums appear in the CSV only as diagnostics and are excluded from totals.",
        "", f"TronGrid transfer rows lack block/log indices, so {same_block_candidates} address histories with a transfer at the freeze timestamp have same-block order ambiguity. USD valuations apply Coin Metrics USDT PriceUSD with a daily series timestamp on each freeze's UTC date (raw `{prices_ref}`), not a quote at the freeze second. The current balance is a later snapshot and is not substituted for historical balance.",
        "", "Offline reproduction requires both `data/raw/verify_freeze/` and the referenced `data/raw/tron/trc20/` captures. The repository's `.gitignore` excludes `data/raw/`, so these saved responses must be preserved with the research handoff.",
        "", "## Top 15 claimed contributors, independently reconstructed", "",
        "| Address | OFAC name | First-freeze USDT | Action | Event transaction |", "|---|---|---:|---|---|"]
    for a in top15:
        item = verified[a]; lead = sorted(ltrx[a], key=lambda r:r["listed_date"])[0]
        tx = item["event"]["transaction_id"] if item["event"] else ""
        lines.append(f"| `{a}` | {lead['sdn_name']} | {fmt(item.get('freeze_usdt', Decimal(0)))} | [{item['date']}]({lead['listed_action_url']}) | [{tx}](https://tronscan.org/#/transaction/{tx}) |")
    grouped_actions = defaultdict(lambda: {"amount": Decimal(0), "count": 0, "entities": set()})
    for a in top15:
        lead = sorted(ltrx[a], key=lambda r:r["listed_date"])[0]
        key = (verified[a]["date"], lead["listed_action_url"])
        grouped_actions[key]["amount"] += verified[a].get("freeze_usdt", Decimal(0))
        grouped_actions[key]["count"] += 1
        grouped_actions[key]["entities"].add(lead["sdn_name"])
    lines += ["", "### OFAC actions represented among the top 15", "",
              "| Action date and source | Addresses | OFAC names | First-freeze USDT |",
              "|---|---:|---|---:|"]
    for (date, url), group in sorted(grouped_actions.items()):
        lines.append(f"| [{date}]({url}) | {group['count']} | {', '.join(sorted(group['entities']))} | {fmt(group['amount'])} |")
    lines += ["", f"**Top-15 sum:** {fmt(top_sum)} USDT at each address's first freeze, {top_sum/full_sum*100:.2f}% of the known subtotal; proposed top-15 sum {fmt(claim_top)} USDT; difference {fmt(top_diff)} USDT. The independently reprocessed {len(known_set)}-address known subtotal is {fmt(full_sum)} USDT ({fmt(full_usd,3)} USD under daily UTC price labels). The proposed known subtotal is {fmt(claim_total)} USDT, a difference of {fmt(full_sum-claim_total)} USDT. The proposed USD subtotal is {fmt(claim_usd,3)}; the daily-price convention here gives {fmt(full_usd-claim_usd,3)} USD difference. Check each row's transfer, price, and event raw refs in the CSV.",
       "", "**Unknown first-freeze balances in the frozen original capture:** " + ", ".join(f"`{a}`" for a in unknown_addresses) + ". Their diagnostic partial sums are excluded. A later parallel refresh completed one of these histories, as noted above.",
       "", f"**OFAC action-page exceptions in the 40-address sample:** {len(action_issues)}. " + ("Addresses: " + ", ".join(f"`{a}`" for a in action_issues) + "." if action_issues else "Every sampled page contained the exact address and its URL date matched the ledger's first listing date."),
       "", "## Methodological concerns", "",
       "- An OFAC Recent Actions date is a calendar date. The noon ET publication proxy is an analysis convention, not an observed publication timestamp. Only events before 00:00 ET prove pre-day ordering; they do not show why an issuer acted earlier.",
       "- OFAC pages are checked for the exact address string and action-date URL in the sample. A later addition to an already-designated entity must use that address-addition action, not the entity's original designation date. The CSV keeps the action URL per row.",
       f"- {far_pre} of the {pre} pre-day Tron events are more than 30 days before the first OFAC address-listing date. For example, `{min(verified, key=lambda a: lag_hours(verified[a]['event']['block_timestamp'], verified[a]['date']))}` was frozen long before its listed action (event and action refs in the CSV). Tether may have acted for an unrelated reason; temporal ordering does not establish advance knowledge, coordination, or a legal conclusion.",
       "- 'Ever blacklisted' is an event-history measure; `getBlackListStatus` is current state. An eventual unblacklisting would not erase the historical event. Circle's 20 `latest` eth_call results assess current state over a moving window; the independent Blockscout event crawl establishes the historical count and median.",
       "- USDT totals are native token units. The USD estimate sums daily-price valuations across different freeze dates, not cash held at one time; the Coin Metrics series labels each price at 00:00 UTC rather than the exact freeze second.",
       "", "This is research, not legal or compliance advice."]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines) + "\n"
    if args.check:
        if not REPORT.exists() or REPORT.read_text() != report_text:
            raise AssertionError(f"offline result differs: {REPORT}")
    else:
        REPORT.write_text(report_text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(output)} rows), {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
