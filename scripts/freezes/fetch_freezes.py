#!/usr/bin/env python3
"""Issuer blacklist history. Stdlib only; no OFAC matching. See docs/FREEZES.md.

--refresh collects only new finalized/solidified blocks (resuming partial scans).
--check is offline: rebuild and verify every published count from saved responses.
Default invocation also resumes/refreshes. A nonblocking flock makes safe for repeated invocation.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/freezes"
STATE = RAW / "state.json.gz"
RPC = "https://ethereum-rpc.publicnode.com"
TRON = "https://api.trongrid.io"
ETHERSCAN = "https://api.etherscan.io/v2/api"
BLOCKSCOUT = "https://eth.blockscout.com/api"
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
TRC20 = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TOPICS = {
    "AddedBlackList": "0x42e160154868087d6bfdc0ca23d96a1c1cfa32f1b72ba9ba27b69b98a0d819dc",
    "RemovedBlackList": "0xd7e9ec6e6ecd65492dce6bf513cd6867560d49544421d0783ddf06e76c24470c",
    "DestroyedBlackFunds": "0x61e6e66b0d6339b2980aecc6ccc0039736791f0ccde9ed512e789a7fbdd698c6",
    "Blacklisted": "0xffa4e6181777692565cf28528fc88fd1516ea86b56da075235fa575af6a4b855",
    "UnBlacklisted": "0x117e3210bb9aa7d9baff172026820255c6f6c30ba8999d1c2fd88e2848137c4e",
}
TETHER_EVENTS = tuple(TOPICS)[:3]
CIRCLE_EVENTS = tuple(TOPICS)[3:]
ADDS = {"AddedBlackList", "Blacklisted"}
REMOVES = {"RemovedBlackList", "UnBlacklisted"}
FIELDS = ["chain", "token", "contract", "event", "address", "address_normalized",
          "address_hex", "amount", "amount_raw", "decimals", "block", "timestamp",
          "tx_hash", "transaction_index", "log_index", "balance_at_freeze",
          "balance_block", "balance_method", "balance_raw_ref", "raw_ref", "source_url"]
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def now():
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def utc(seconds):
    return dt.datetime.fromtimestamp(seconds, dt.UTC).isoformat().replace("+00:00", "Z")


def integer(value):
    # Blockscout's legacy logs API sometimes encodes a zero index as bare 0x.
    return int(value[2:] or "0", 16) if isinstance(value, str) and value.startswith("0x") else int(value)


def units(raw):
    whole, fraction = divmod(int(raw), 1_000_000)
    return str(whole) if not fraction else f"{whole}.{fraction:06d}".rstrip("0")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def write_gz(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("wb") as f:
        with gzip.GzipFile(filename="", fileobj=f, mode="wb", mtime=0) as z:
            z.write(canonical(obj).encode())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def rel(path):
    return str(path.relative_to(ROOT))


def tron_address(value):
    value = value.removeprefix("0x")
    if len(value) == 40:
        value = "41" + value
    if not re.fullmatch(r"41[0-9a-fA-F]{40}", value):
        raise ValueError("Invalid Tron hex address")
    payload = bytes.fromhex(value)
    full = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(full, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = ALPHABET[rem] + out
    return out, "0x" + value[2:].lower()


class Fetcher:
    def __init__(self):
        self.last = {}
        self.key = None
        self.blockscout_unavailable = False
        self.last_error_ref = None

    def etherscan_key(self):
        if self.key is None:
            self.key = os.environ.get("ETHERSCAN_API_KEY")
            if not self.key:
                raise RuntimeError("ETHERSCAN_API_KEY unavailable")
        return self.key

    def get(self, url, body=None, *, context=None, scope="", fresh=False):
        # Never store the key or the authenticated URL, including in exceptions.
        safe = {"url": url, "json": body}
        digest = hashlib.sha256(canonical([safe, scope]).encode()).hexdigest()
        folder = (context or {}).get("kind", "requests")
        path = RAW / folder / (digest + ".json.gz")
        if path.exists() and not fresh:
            return read_gz(path)["response"], rel(path)
        host = urllib.parse.urlsplit(url).hostname
        if host not in {"api.etherscan.io", "eth.blockscout.com", "ethereum-rpc.publicnode.com",
                        "eth.drpc.org", "api.trongrid.io"}:
            raise RuntimeError("Unapproved API destination")
        interval = (0.85 if host == "api.etherscan.io" else 1.25 if host == "eth.blockscout.com"
                    else 1.10 if host == "api.trongrid.io" else 0.35)
        wire_url = url
        if host == "api.etherscan.io":
            wire_url += "&apikey=" + urllib.parse.quote(self.etherscan_key())
        for attempt in range(7):
            time.sleep(max(0, self.last.get(host, 0) + interval - time.monotonic()))
            self.last[host] = time.monotonic()
            request = urllib.request.Request(wire_url, data=None if body is None else canonical(body).encode(),
                                             headers={"User-Agent": "life-after-sanctions-research/1.0",
                                                      "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = json.load(response)
                text = str(data.get("result", "")) if isinstance(data, dict) else ""
                if isinstance(data, dict) and (data.get("status") == "0" and "rate limit" in text.lower()
                                              or data.get("Error", "").startswith("The key exceeds")):
                    raise RuntimeError("rate limited")
                if isinstance(data, dict) and data.get("success") is False:
                    raise RuntimeError("API unsuccessful response")
                write_gz(path, {"request": safe, "context": context or {}, "fetched_at": now(),
                                "response": data})
                return data, rel(path)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError,
                    json.JSONDecodeError) as exc:
                code = getattr(exc, "code", None)
                if attempt == 6 or code in (400, 401, 403, 404) or (host == "eth.blockscout.com" and code == 429):
                    error = {"type": type(exc).__name__, "http_status": code}
                    if isinstance(exc, urllib.error.HTTPError):
                        body_text = exc.read().decode("utf-8", "replace")[:4000]
                        if self.key:
                            body_text = body_text.replace(self.key, "REDACTED")
                        error["body"] = body_text
                    error_path = RAW / "errors" / (digest + ".json.gz")
                    write_gz(error_path,
                             {"request": safe, "context": context or {}, "fetched_at": now(), "response": {"error": error}})
                    self.last_error_ref = rel(error_path)
                    # Do not propagate an exception that might contain wire_url.
                    raise RuntimeError(f"API request failed: {host}, status={code}, type={type(exc).__name__}") from None
                time.sleep(60 if code == 429 else min(60, 2 ** (attempt + 1)))
        raise AssertionError("unreachable")

    def rpc(self, method, params, *, endpoint=RPC, context=None, scope="", fresh=False):
        data, ref = self.get(endpoint, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                             context=context, scope=scope, fresh=fresh)
        if "error" in data or "result" not in data:
            raise RuntimeError("RPC returned error: " + canonical(data.get("error")))
        return data["result"], ref


def explorer_scan(fetcher, source, token, event, lo, hi, refs):
    contract = USDT if token == "USDT" else USDC
    params = {"module": "logs", "action": "getLogs", "fromBlock": lo, "toBlock": hi,
              "address": contract, "topic0": TOPICS[event]}
    if source == "etherscan":
        params.update(chainid=1, page=1, offset=1000)
    endpoint = ETHERSCAN if source == "etherscan" else BLOCKSCOUT
    data, ref = fetcher.get(endpoint + "?" + urllib.parse.urlencode(params),
                            context={"kind": "logs", "chain": "ETH", "token": token,
                                     "event": event, "source": source, "from": lo, "to": hi})
    logs = data.get("result")
    empty = data.get("status") == "0" and "no logs" in str(data.get("message", "")).lower()
    if empty:
        logs = []
    if not isinstance(logs, list):
        # Query timeout / too many results is handled by subdivision, not as zero.
        if hi > lo and any(x in str(logs).lower() for x in ("timeout", "smaller", "too many", "size")):
            middle = (lo + hi) // 2
            explorer_scan(fetcher, source, token, event, lo, middle, refs)
            explorer_scan(fetcher, source, token, event, middle + 1, hi, refs)
            return
        raise RuntimeError(f"{source} logs unsuccessful: {str(logs)[:150]}")
    if len(logs) >= 1000:
        if lo == hi:
            raise RuntimeError("At least 1000 matching logs in one block; explicit pagination required")
        middle = (lo + hi) // 2
        explorer_scan(fetcher, source, token, event, lo, middle, refs)
        explorer_scan(fetcher, source, token, event, middle + 1, hi, refs)
    else:
        refs.append(ref)


def tron_scan(fetcher, event, lo_ms, hi_ms, direction, restart=False):
    params = {"event_name": event, "limit": 200, "only_confirmed": "true",
              "order_by": "block_timestamp," + direction,
              "min_block_timestamp": lo_ms, "max_block_timestamp": hi_ms}
    url = TRON + "/v1/contracts/" + TRC20 + "/events?" + urllib.parse.urlencode(params)
    refs, seen = [], set()
    while url:
        if url in seen:
            raise RuntimeError("TronGrid fingerprint cycle")
        seen.add(url)
        try:
            data, ref = fetcher.get(url, context={"kind": "tron_events", "event": event,
                                                 "direction": direction, "from_ms": lo_ms, "to_ms": hi_ms}, fresh=restart)
        except RuntimeError as exc:
            # Fingerprints may expire during a long interruption. Rebuild the
            # uncommitted bounded pass with new fingerprints; do not skip pages.
            if "status=400" in str(exc) and "fingerprint=" in url and not restart:
                return tron_scan(fetcher, event, lo_ms, hi_ms, direction, restart=True)
            raise
        if data.get("success") is not True or not isinstance(data.get("data"), list):
            raise RuntimeError("Invalid TronGrid events response")
        refs.append(ref)
        following = data.get("meta", {}).get("links", {}).get("next")
        if following:
            parsed = urllib.parse.urlsplit(following)
            if parsed.scheme != "https" or parsed.netloc != "api.trongrid.io" or parsed.path != "/v1/contracts/" + TRC20 + "/events":
                raise RuntimeError("Unexpected TronGrid next link")
            q = urllib.parse.parse_qs(parsed.query)
            for key in ("event_name", "min_block_timestamp", "max_block_timestamp", "order_by"):
                if q.get(key) != [str(params[key])]:
                    raise RuntimeError("TronGrid changed pagination filter")
        if not data["data"] and following:
            raise RuntimeError("Empty TronGrid page with next link")
        url = following
        if len(refs) % 20 == 0:
            print(f"Tron {event} {direction}: {len(refs)} pages", flush=True)
    return refs


def load_state():
    return read_gz(STATE) if STATE.exists() else {"version": 1, "scans": [], "checks": [], "balances": []}


def snapshot(fetcher, state, chain):
    # Persist the target before scanning so a killed run reuses its cached pages.
    pending = state.get("pending", {}).get(chain)
    if pending:
        return pending
    if chain == "ETH":
        head, ref = fetcher.rpc("eth_getBlockByNumber", ["finalized", False],
                                context={"kind": "heads"}, scope=now(), fresh=True)
        target = {"block": integer(head["number"]), "timestamp_ms": integer(head["timestamp"]) * 1000,
                  "hash": head["hash"], "raw_ref": ref}
    else:
        head, ref = fetcher.get(TRON + "/walletsolidity/getnowblock", {},
                                context={"kind": "heads"}, scope=now(), fresh=True)
        h = head["block_header"]["raw_data"]
        target = {"block": h["number"], "timestamp_ms": h["timestamp"], "hash": head["blockID"], "raw_ref": ref}
    state.setdefault("pending", {})[chain] = target
    write_gz(STATE, state)
    return target


def collect(fetcher, state):
    unfinished = set(state.get("pending", {}))
    for chain, tokens in (("TRX", ("USDT",)), ("ETH", ("USDT", "USDC"))):
        if unfinished and chain not in unfinished and chain in state.get("heads", {}):
            continue
        target = snapshot(fetcher, state, chain)
        for token in tokens:
            for event in TETHER_EVENTS if token == "USDT" else CIRCLE_EVENTS:
                for source in ("etherscan", "blockscout") if chain == "ETH" else ("asc", "desc"):
                    if source == "blockscout" and fetcher.blockscout_unavailable:
                        continue
                    done = [s for s in state["scans"] if (s["chain"], s["token"], s["event"], s["source"]) == (chain, token, event, source)]
                    last = max(done, key=lambda s: s["to_block"]) if done else None
                    lo = last["to_block"] + 1 if last else 0
                    if lo > target["block"]:
                        continue
                    print(f"{chain} {token} {event} {source}: blocks {lo}..{target['block']}", flush=True)
                    start_ms = last["to_timestamp_ms"] + 1 if last else 0
                    refs = []
                    if chain == "ETH":
                        try:
                            explorer_scan(fetcher, source, token, event, lo, target["block"], refs)
                        except RuntimeError as exc:
                            if source != "blockscout":
                                raise
                            fetcher.blockscout_unavailable = True
                            state.setdefault("source_gaps", {})["blockscout"] = {"error": str(exc), "at": now(),
                                                                                  "attempted_event": event,
                                                                                  "raw_ref": fetcher.last_error_ref}
                            print("Blockscout unavailable; use independent RPC block samples for unchecked ranges", flush=True)
                            write_gz(STATE, state)
                            # A failed optional cross-source pass does not truncate the primary history.
                            continue
                    else:
                        refs = tron_scan(fetcher, event, start_ms, target["timestamp_ms"], source)
                    state["scans"].append({"chain": chain, "token": token, "event": event, "source": source,
                                           "from_block": lo, "to_block": target["block"],
                                           "from_timestamp_ms": start_ms, "to_timestamp_ms": target["timestamp_ms"],
                                           "head_ref": target["raw_ref"], "refs": refs})
                    write_gz(STATE, state)
        state.setdefault("heads", {})[chain] = target
        state["pending"].pop(chain)
        write_gz(STATE, state)


def decode(scan, envelope, ref):
    chain, token, event = (scan[k] for k in ("chain", "token", "event"))
    response = envelope["response"]
    logs = response["result"] if chain == "ETH" else response["data"]
    if not isinstance(logs, list):
        raise ValueError("Non-list logs in completed scan")
    for log in logs:
        row = dict.fromkeys(FIELDS, "")
        row.update(chain=chain, token=token, event=event, decimals="6", raw_ref=ref)
        if chain == "ETH":
            contract = USDT if token == "USDT" else USDC
            assert log["address"].lower() == contract and log["topics"][0].lower() == TOPICS[event]
            assert not log.get("removed", False)
            topics = [v for v in log["topics"] if v]
            words = [log["data"][i:i + 64] for i in range(2, len(log["data"]), 64)]
            address_word = topics[1][2:] if len(topics) > 1 else words.pop(0)
            assert len(address_word) == 64 and int(address_word[:24], 16) == 0
            address = "0x" + address_word[-40:].lower()
            row.update(contract=contract, address=address, address_normalized=address, address_hex=address,
                       block=integer(log["blockNumber"]), timestamp=utc(integer(log["timeStamp"])),
                       tx_hash=log["transactionHash"].lower(), log_index=integer(log["logIndex"]),
                       transaction_index=integer(log["transactionIndex"]),
                       source_url="https://etherscan.io/tx/" + log["transactionHash"])
            if event == "DestroyedBlackFunds":
                assert len(words) == 1
                row.update(amount_raw=str(int(words[0], 16)), amount=units(int(words[0], 16)))
        else:
            assert log["contract_address"] == TRC20 and log["event_name"] == event
            address, address_hex = tron_address(log["result"]["0"])
            row.update(contract=TRC20, address=address, address_normalized=address, address_hex=address_hex,
                       block=log["block_number"], timestamp=utc(log["block_timestamp"] / 1000),
                       tx_hash=log["transaction_id"], log_index=log["event_index"],
                       source_url="https://tronscan.org/#/transaction/" + log["transaction_id"])
            if event == "DestroyedBlackFunds":
                value = int(log["result"]["1"])
                row.update(amount_raw=str(value), amount=units(value))
        assert scan["from_block"] <= row["block"] <= scan["to_block"]
        yield row


def event_key(row):
    return row["chain"], row["token"], row["tx_hash"], int(row["log_index"])


def comparable(row):
    return tuple(str(row[k]) for k in ("chain", "token", "event", "address_normalized", "amount_raw",
                                      "block", "timestamp", "tx_hash", "log_index"))


def reconcile_ethereum(state, first, second, token, event, fetcher=None):
    discrepant = {k[2] for k in first.keys() ^ second.keys()}
    discrepant.update(k[2] for k in first.keys() & second.keys()
                      if comparable(first[k]) != comparable(second[k]))
    chosen = dict(first)
    details = []
    for tx in sorted(discrepant):
        ref = state.setdefault("reconciliation", {}).get(tx)
        if not ref:
            if fetcher is None:
                raise ValueError("Missing independent receipt reconciliation for " + tx)
            receipt, ref = fetcher.rpc("eth_getTransactionReceipt", [tx], endpoint="https://eth.drpc.org",
                                       context={"kind": "reconciliation"})
            if not isinstance(receipt, dict) or receipt.get("status") != "0x1":
                raise ValueError("Missing/successless reconciliation receipt for " + tx)
            state["reconciliation"][tx] = ref
            write_gz(STATE, state)
        receipt = read_gz(ROOT / ref)["response"]["result"]
        assert receipt["transactionHash"].lower() == tx
        candidates = [r for r in list(first.values()) + list(second.values()) if r["tx_hash"] == tx]
        block = integer(receipt["blockNumber"])
        assert all(r["block"] == block for r in candidates)
        stamp = int(dt.datetime.fromisoformat(candidates[0]["timestamp"]).timestamp())
        contract = USDT if token == "USDT" else USDC
        logs = []
        for log in receipt["logs"]:
            if log["address"].lower() == contract and log["topics"][0].lower() == TOPICS[event]:
                log = dict(log)
                log["timeStamp"] = log.get("blockTimestamp", hex(stamp))
                logs.append(log)
        scan = {"chain": "ETH", "token": token, "event": event, "from_block": block, "to_block": block}
        onchain = list(decode(scan, {"response": {"result": logs}}, ref))
        primary = [r for r in first.values() if r["tx_hash"] == tx]
        secondary = [r for r in second.values() if r["tx_hash"] == tx]
        for k in list(chosen):
            if k[2] == tx:
                del chosen[k]
        # The actual receipt is authoritative if either indexer disagrees.
        chosen.update({event_key(r): r for r in onchain})
        details.append({"tx_hash": tx, "block": block, "receipt_raw_ref": ref,
                        "primary_logs": len(primary), "secondary_logs": len(secondary), "receipt_logs": len(onchain),
                        "primary_matches_receipt": sorted(map(comparable, primary)) == sorted(map(comparable, onchain)),
                        "secondary_matches_receipt": sorted(map(comparable, secondary)) == sorted(map(comparable, onchain))})
    return chosen, details


def rebuild(state, fetcher=None):
    by_source = collections.defaultdict(dict)
    intervals = collections.defaultdict(list)
    for scan in state["scans"]:
        group = tuple(scan[k] for k in ("chain", "token", "event", "source"))
        intervals[group].append((scan["from_block"], scan["to_block"]))
        leaves = []
        previous_next = None
        for ref in scan["refs"]:
            envelope = read_gz(ROOT / ref)
            context = envelope["context"]
            if scan["chain"] == "ETH":
                assert context["source"] == scan["source"] and context["event"] == scan["event"]
                leaves.append((context["from"], context["to"]))
                assert len(envelope["response"]["result"]) < 1000
            else:
                assert context["event"] == scan["event"] and context["direction"] == scan["source"]
                assert context["from_ms"] == scan["from_timestamp_ms"] and context["to_ms"] == scan["to_timestamp_ms"]
                if previous_next is not None:
                    assert envelope["request"]["url"] == previous_next, "Broken Tron page chain"
                else:
                    assert "fingerprint=" not in envelope["request"]["url"], "Missing first Tron page"
                previous_next = envelope["response"].get("meta", {}).get("links", {}).get("next")
                for log in envelope["response"]["data"]:
                    assert scan["from_timestamp_ms"] <= log["block_timestamp"] <= scan["to_timestamp_ms"]
            for row in decode(scan, envelope, ref):
                key = event_key(row)
                if key in by_source[group]:
                    assert comparable(row) == comparable(by_source[group][key]), "Conflicting duplicate"
                by_source[group][key] = row
        if scan["chain"] == "ETH":
            end = scan["from_block"] - 1
            for lo, hi in sorted(leaves):
                assert lo == end + 1, "Missing or overlapping explorer leaf range"
                end = hi
            assert end == scan["to_block"], "Incomplete explorer leaf ranges"
        else:
            assert scan["refs"] and previous_next is None, "Tron pagination not exhausted"
    for group, spans in intervals.items():
        end = -1
        for lo, hi in sorted(spans):
            assert lo == end + 1, f"Coverage gap or overlap: {group}, {lo}, {end}"
            end = hi
        if group[3] != "blockscout":
            assert end == state["heads"][group[0]]["block"], f"Incomplete scan: {group}"
    comparisons, rows = [], []
    for chain, token in (("ETH", "USDT"), ("ETH", "USDC"), ("TRX", "USDT")):
        for event in TETHER_EVENTS if token == "USDT" else CIRCLE_EVENTS:
            source1, source2 = ("etherscan", "blockscout") if chain == "ETH" else ("asc", "desc")
            key1, key2 = (chain, token, event, source1), (chain, token, event, source2)
            assert key1 in intervals and (chain == "ETH" or key2 in intervals), "Required source not fully scanned"
            first, second = by_source[key1], by_source[key2]
            secondary_end = max((hi for lo, hi in intervals.get(key2, [])), default=-1)
            covered = {k: r for k, r in first.items() if r["block"] <= secondary_end}
            exact = covered.keys() == second.keys() and all(comparable(r) == comparable(second[k]) for k, r in covered.items())
            details = []
            chosen = first
            if chain == "ETH":
                resolved, details = reconcile_ethereum(state, covered, second, token, event, fetcher)
                chosen = {k: r for k, r in first.items() if r["block"] > secondary_end}
                chosen.update(resolved)
            else:
                assert exact, f"Tron paging-pass disagreement: {event} ({len(first)} vs {len(second)})"
            comparisons.append({"chain": chain, "token": token, "event": event, "sources": [source1, source2],
                                "count": len(chosen), "primary_count": len(first), "secondary_count": len(second),
                                "secondary_covered_through_block": secondary_end,
                                "secondary_full_coverage": secondary_end == state["heads"][chain]["block"],
                                "matched_in_checked_range": exact, "reconciled": True, "receipt_reconciliations": details})
            rows.extend(chosen.values())
    rows.sort(key=lambda r: (r["chain"], r["token"], r["block"],
                             r["transaction_index"] if r["transaction_index"] != "" else 0,
                             r["log_index"], r["tx_hash"]))
    # For Tron there is no transaction index in TronGrid's event API. Resolve any
    # same-address same-block conflict before state reduction rather than guessing.
    transitions = collections.defaultdict(list)
    for row in rows:
        if row["event"] in ADDS | REMOVES:
            transitions[(row["chain"], row["token"], row["address"], row["block"])].append(row)
    for key, same_block in transitions.items():
        if key[0] == "TRX" and len({r["event"] in ADDS for r in same_block}) > 1:
            raise ValueError("Tron same-block add/remove needs transaction ordering from block: " + str(key))
    active, touched = replay_blacklists(rows)
    return rows, active, touched, comparisons


def replay_blacklists(rows):
    """Rows must be in chain order. Burns leave blacklist membership intact."""
    active, touched = collections.defaultdict(set), collections.defaultdict(set)
    for row in rows:
        group = row["chain"], row["token"]
        if row["event"] in ADDS:
            active[group].add(row["address"])
            touched[group].add(row["address"])
        elif row["event"] in REMOVES:
            active[group].discard(row["address"])
            touched[group].add(row["address"])
    return active, touched


def crosscheck(fetcher, state, active, touched):
    seed = 20261023
    for group in sorted(active):
        chain, token = group
        head = state["heads"][chain]
        rng = random.Random(f"{seed}:{chain}:{token}")
        samples = [(a, True) for a in rng.sample(sorted(active[group]), min(20, len(active[group])))]
        cleared = sorted(touched[group] - active[group])
        samples += [(a, False) for a in rng.sample(cleared, min(10, len(cleared)))]
        for address, expected in samples:
            label = [chain, token, address, head["block"]]
            if any(c["id"] == label for c in state["checks"]):
                continue
            context = {"kind": "state_checks", "chain": chain, "token": token, "address": address,
                       "expected": expected, "snapshot_block": head["block"]}
            if chain == "ETH":
                selector = "e47d6060" if token == "USDT" else "fe575a87"
                result, ref = fetcher.rpc("eth_call", [{"to": USDT if token == "USDT" else USDC,
                                                       "data": "0x" + selector + address[2:].rjust(64, "0")}, "latest"],
                                          context=context, scope=str(head["block"]))
                assert isinstance(result, str) and len(result) == 66, "Non-ABI state call response"
                actual = integer(result)
            else:
                n = 0
                for char in address:
                    n = n * 58 + ALPHABET.index(char)
                payload = n.to_bytes(25, "big")[:21]
                result, ref = fetcher.get(TRON + "/wallet/triggerconstantcontract",
                                          {"owner_address": TRC20, "contract_address": TRC20,
                                           "function_selector": "isBlackListed(address)",
                                           "parameter": payload[1:].hex().rjust(64, "0"), "visible": True},
                                          context=context, scope=str(head["block"]))
                if result.get("result", {}).get("result") is not True:
                    raise RuntimeError("Tron state call failed")
                actual = int(result["constant_result"][0], 16)
            assert actual in (0, 1)
            state["checks"].append({"id": label, "expected": expected, "actual": bool(actual),
                                     "raw_ref": ref, "call_block": "latest", "sample_seed": seed})
            write_gz(STATE, state)
            if bool(actual) != expected:
                raise ValueError(f"Latest state mismatch {chain} {token} {address}; refresh and investigate")
        print(f"{chain} {token}: checked {len(samples)} latest blacklist states", flush=True)


def rpc_sample_checks(state, rows, fetcher=None):
    """Independent immutable populated one-block log ranges."""
    checks = []
    for token in ("USDT", "USDC"):
        for event in TETHER_EVENTS if token == "USDT" else CIRCLE_EVENTS:
            matching = [r for r in rows if r["chain"] == "ETH" and r["token"] == token and r["event"] == event]
            blocks = sorted({r["block"] for r in matching})
            if not blocks:
                continue
            rng = random.Random("rpc-samples:" + token + ":" + event)
            sample = sorted(set([blocks[0], blocks[len(blocks)//2], blocks[-1]]
                                + rng.sample(blocks, min(3, len(blocks)))))
            for block in sample:
                label = f"{token}:{event}:{block}"
                ref = state.setdefault("rpc_samples", {}).get(label)
                if not ref:
                    if fetcher is None:
                        raise ValueError("Missing independent RPC sample " + label)
                    params = [{"address": USDT if token == "USDT" else USDC, "fromBlock": hex(block),
                               "toBlock": hex(block), "topics": [TOPICS[event]]}]
                    response, ref = fetcher.rpc("eth_getLogs", params, endpoint="https://eth.drpc.org",
                                                context={"kind": "rpc_samples", "token": token, "event": event, "block": block})
                    state["rpc_samples"][label] = ref
                    write_gz(STATE, state)
                logs = read_gz(ROOT / ref)["response"]["result"]
                expected = [r for r in matching if r["block"] == block]
                stamp = int(dt.datetime.fromisoformat(expected[0]["timestamp"]).timestamp()) if expected else 0
                normalized = [dict(log, timeStamp=log.get("blockTimestamp", hex(stamp))) for log in logs]
                scan = {"chain": "ETH", "token": token, "event": event, "from_block": block, "to_block": block}
                actual = list(decode(scan, {"response": {"result": normalized}}, ref))
                assert sorted(map(comparable, actual)) == sorted(map(comparable, expected)), "Independent one-block RPC mismatch: " + label
                checks.append({"token": token, "event": event, "block": block, "logs": len(actual), "raw_ref": ref})
    return checks


def balances(fetcher, state, rows):
    # Sample historical archive calls; unsupported providers are recorded explicitly.
    for token in ("USDT", "USDC"):
        freezes = [r for r in rows if r["chain"] == "ETH" and r["token"] == token and r["event"] in ADDS]
        rng = random.Random("freeze-balances:" + token)
        for row in rng.sample(freezes, min(20, len(freezes))):
            label = list(event_key(row))
            if any(b["id"] == label for b in state["balances"]):
                continue
            request = [{"to": row["contract"], "data": "0x70a08231" + row["address_hex"][2:].rjust(64, "0")}, hex(row["block"])]
            try:
                result, ref = fetcher.rpc("eth_call", request, endpoint="https://eth.drpc.org",
                                          context={"kind": "balances", "event_key": label}, scope="archive")
                assert isinstance(result, str) and len(result) == 66, "Non-ABI balance call response"
                entry = {"id": label, "balance": units(integer(result)), "block": row["block"],
                         "method": "balanceOf_end_of_freeze_block", "raw_ref": ref}
            except RuntimeError as exc:
                entry = {"id": label, "error": str(exc), "raw_ref": fetcher.last_error_ref}
            state["balances"].append(entry)
            write_gz(STATE, state)
        print(f"ETH {token}: historical balance sample attempted", flush=True)


def review_contracts(fetcher, state):
    head = state["heads"]["ETH"]["block"]
    if state.get("contract_review", {}).get("snapshot_block") == head:
        return
    proxy, proxy_ref = fetcher.get("https://eth.blockscout.com/api/v2/smart-contracts/" + USDC,
                                   context={"kind": "contract_review", "token": "USDC"})
    implementation = proxy["implementations"][0]["address_hash"]
    storage, storage_ref = fetcher.rpc("eth_getStorageAt", [USDC,
                         "0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3", "latest"],
                         context={"kind": "contract_review", "purpose": "current_implementation"}, scope=str(head))
    assert storage[-40:].lower() == implementation[2:].lower(), "USDC implementation changed; fetch and review new source"
    code, code_ref = fetcher.get("https://eth.blockscout.com/api/v2/smart-contracts/" + implementation,
                                 context={"kind": "contract_review", "token": "USDC", "implementation": implementation},
                                 scope="")
    sources = [{"file_path": code["file_path"], "source_code": code["source_code"]}] + code["additional_sources"]
    review = {"snapshot_block": head, "proxy_ref": proxy_ref, "implementation_ref": code_ref,
              "implementation": implementation, "implementation_storage_raw_ref": storage_ref, "name": code["name"],
              "functions": sorted(a["name"] for a in code["abi"] if a["type"] == "function")}
    # Fail rather than perpetuate a conclusion after an unreviewed implementation change.
    assert code["name"] == "FiatTokenV2_2", "USDC implementation changed; review burn/blacklist logic"
    v1 = next(s["source_code"] for s in sources if s["file_path"].endswith("/v1/FiatTokenV1.sol"))
    assert re.search(r"function burn\(uint256 _amount\).*?onlyMinters\s+notBlacklisted\(msg.sender\)", v1, re.S)
    assert "_setBalance(msg.sender, balance.sub(_amount));" in v1
    assert not {"wipeBlacklistedAddress", "destroyBlackFunds", "clawback"} & set(review["functions"])
    v21 = next(s["source_code"] for s in sources if s["file_path"].endswith("/FiatTokenV2_1.sol"))
    assert "_blacklist(address(this));" in v21
    self_state, self_ref = fetcher.rpc("eth_call", [{"to": USDC, "data": "0xfe575a87" + USDC[2:].rjust(64, "0")}, "latest"],
                                       context={"kind": "contract_review", "token": "USDC", "purpose": "self_blacklist"},
                                       scope=str(head))
    assert integer(self_state) == 1
    review["self_blacklist_raw_ref"] = self_ref
    state["contract_review"] = review
    write_gz(STATE, state)


def checks_from_raw(state):
    checks = []
    for c in state["checks"]:
        chain, token, address, snapshot_block = c["id"]
        if snapshot_block != state["heads"][chain]["block"]:
            continue
        raw = read_gz(ROOT / c["raw_ref"])
        response = raw["response"]
        if chain == "ETH":
            call, block_tag = raw["request"]["json"]["params"]
            selector = "e47d6060" if token == "USDT" else "fe575a87"
            assert call == {"to": USDT if token == "USDT" else USDC,
                            "data": "0x" + selector + address[2:].rjust(64, "0")}
            assert block_tag == "latest" and len(response["result"]) == 66
        else:
            assert raw["context"]["address"] == address
            assert raw["request"]["json"]["function_selector"] == "isBlackListed(address)"
        actual = integer(response["result"]) if chain == "ETH" else int(response["constant_result"][0], 16)
        assert actual in (0, 1) and bool(actual) == c["actual"] == c["expected"]
        checks.append(c)
    for chain, token in (("ETH", "USDT"), ("ETH", "USDC"), ("TRX", "USDT")):
        assert len({c["id"][2] for c in checks if c["id"][:2] == [chain, token] and c["expected"]}) >= 20, "Missing 20 distinct active state checks"
    return checks


def outputs(state, *, verify=False):
    for chain, head in state["heads"].items():
        response = read_gz(ROOT / head["raw_ref"])["response"]
        if chain == "ETH":
            assert integer(response["result"]["number"]) == head["block"]
            assert integer(response["result"]["timestamp"]) * 1000 == head["timestamp_ms"]
            assert response["result"]["hash"] == head["hash"]
        else:
            assert response["block_header"]["raw_data"]["number"] == head["block"]
            assert response["block_header"]["raw_data"]["timestamp"] == head["timestamp_ms"]
            assert response["blockID"] == head["hash"]
    rows, active, touched, comparisons = rebuild(state)
    checks = checks_from_raw(state)
    for c in checks:
        chain, token, address, _ = c["id"]
        assert (address in active[(chain, token)]) == c["expected"], "State sample inconsistent with replayed history"
    rpc_checks = rpc_sample_checks(state, rows)
    balance_map = {tuple(b["id"]): b for b in state["balances"] if "balance" in b}
    for row in rows:
        b = balance_map.get(event_key(row))
        if b:
            raw = read_gz(ROOT / b["raw_ref"])
            assert units(integer(raw["response"]["result"])) == b["balance"]
            row.update(balance_at_freeze=b["balance"], balance_block=b["block"],
                       balance_method=b["method"], balance_raw_ref=b["raw_ref"])
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path = ROOT / "data/freezes.csv"
    text = out.getvalue()
    if verify:
        assert path.read_text() == text, "freezes.csv differs from raw-response rebuild"
    else:
        tmp = path.with_suffix(".csv.tmp")
        tmp.write_text(text)
        os.replace(tmp, path)
    report = {"schema_version": 1, "heads": state["heads"], "event_rows": len(rows), "counts": comparisons,
              "current_blacklists": {":".join(g): sorted(a) for g, a in sorted(active.items())},
              "current_counts": {":".join(g): len(a) for g, a in sorted(active.items())},
              "checks": checks, "historical_balances_available": len(balance_map),
              "historical_balances_attempted": len(state["balances"]),
              "csv_sha256": hashlib.sha256(text.encode()).hexdigest()}
    review = state["contract_review"]
    assert integer(read_gz(ROOT / review["self_blacklist_raw_ref"])["response"]["result"]) == 1
    assert read_gz(ROOT / review["implementation_ref"])["response"]["name"] == review["name"]
    report["contract_review"] = review
    report["independent_rpc_samples"] = rpc_checks
    report["source_gaps"] = state.get("source_gaps", {})
    assert read_gz(ROOT / review["implementation_storage_raw_ref"])["response"]["result"][-40:].lower() == review["implementation"][2:].lower()
    report["known_non_event_blacklists"] = {"ETH:USDC": [USDC] if USDC not in active[("ETH", "USDC")] else []}
    report_path = RAW / "check_report.json.gz"
    if verify:
        assert read_gz(report_path) == report, "Check report differs from raw rebuild"
    else:
        write_gz(report_path, report)
        write_docs(report, rows)
    return report


def write_docs(report, rows):
    lines = ["# Stablecoin issuer blacklist, unblacklist and destruction history", "",
             "Produced by `scripts/freezes/fetch_freezes.py`. No OFAC address matching is performed here.", "",
             "## Coverage and counts", "",
             "Counts below are event logs, not unique addresses or legal determinations. All amounts are native token units (6 decimals), not USD.", "",
             "| Chain | Token | Event | Logs | First event UTC | Last event UTC |", "|---|---|---|---:|---|---|"]
    for c in report["counts"]:
        group = [r for r in rows if all(r[k] == c[k] for k in ("chain", "token", "event"))]
        times = sorted(r["timestamp"] for r in group)
        lines.append(f"| {c['chain']} | {c['token']} | {c['event']} | {c['count']:,} | {times[0] if times else '—'} | {times[-1] if times else '—'} |")
    lines += ["", "| Chain | Snapshot block | Snapshot time UTC | Head evidence |", "|---|---:|---|---|"]
    for chain, head in report["heads"].items():
        lines.append(f"| {chain} | {head['block']:,} | {utc(head['timestamp_ms']/1000)} | `{head['raw_ref']}` |")
    lines += ["", "## Completeness checks", "",
              "Ethereum: Etherscan v2 scans every requested topic from block 0 through the finalized head. A range returning 1,000 or more logs is bisected until each leaf returns fewer than 1,000; only nonoverlapping leaf ranges contribute rows. Empty explorer ranges are retained as evidence. Independent Blockscout scans were attempted, but its unauthenticated quota returned HTTP 429. The source-comparison table states the exact block reached for each topic; a missing secondary history does not mean zero events. Within completed Blockscout ranges every event identity and payload is compared. Historical omissions and metadata differences are resolved against dRPC transaction receipts, which supply the canonical logs for each discrepant transaction. Every Ethereum topic also has independent dRPC `eth_getLogs` checks over deterministic single-block ranges spanning early, middle, recent and random populated blocks. Empty dRPC log queries timed out (HTTP 408), so sample ranges deliberately contain known events. A common omission by all checked sources cannot be ruled out; sample checks do not establish full independent coverage.", "",
              "Tron: TronGrid scans each event from timestamp 0 through the same solidified head, with `only_confirmed=true`, limit 200, bounded min/max timestamps, and fingerprint paging to exhaustion. A second complete pass in descending order must reproduce every event identity and payload from the ascending pass. This checks paging, not independent indexer retention. TronScan's tested `/api/contract/events` endpoint ignored the event filter and returned ordinary token transfers; its total is not used. Full-history completeness remains bounded by TronGrid's indexed history.", "",
              "Latest contract state: fixed-seed random samples of 20 addresses in each current blacklist, plus up to 10 cleared addresses per token, are checked using `isBlackListed(address)` for USDT and `isBlacklisted(address)` for USDC. All sampled results must match. Calls are latest state at request time; history ends at the finalized/solidified snapshot, so an intervening issuer action could produce a mismatch and requires a new refresh. The report contains every address and raw call reference.", "",
              "| Chain/token | Event-derived currently blacklisted addresses | Latest checks (active / cleared) |", "|---|---:|---:|"]
    for group, count in report["current_counts"].items():
        checks = [c for c in report["checks"] if ":".join(c["id"][:2]) == group]
        lines.append(f"| {group} | {count:,} | {sum(c['expected'] for c in checks)} / {sum(not c['expected'] for c in checks)} |")
    lines += ["", "The current set is obtained by replaying additions and removals in chain order. A later addition after removal restores membership; destruction does not remove a blacklist entry. It is not the naive difference of all historical add/remove address sets. USDC also internally blacklists its own token contract during initialization without a `Blacklisted` event; that known storage entry is listed separately in `known_non_event_blacklists` and checked directly. Event-derived counts exclude this initialization-only entry.", "",
              "| Chain/token/event | Primary logs | Secondary logs in checked range | Secondary through block | Canonical logs | Discrepant transactions receipt-checked |",
              "|---|---:|---:|---:|---:|---:|"]
    for c in report["counts"]:
        end = c['secondary_covered_through_block']
        lines.append(f"| {c['chain']}/{c['token']}/{c['event']} | {c['primary_count']:,} | {c['secondary_count'] if end >= 0 else 'not completed'} | {end if end >= 0 else '—'} | {c['count']:,} | {len(c['receipt_reconciliations'])} |")
    lines += ["", f"Independent Ethereum RPC log-range checks: {len(report['independent_rpc_samples'])} single-block ranges. Each range, expected count and raw reference is saved in `check_report.json.gz`. Source failures are saved under `errors/` and the earlier throttle probes under `probes/`."]
    discrepancies = [d for c in report["counts"] for d in c["receipt_reconciliations"]]
    if discrepancies:
        lines += ["", "Every discrepancy is preserved in `check_report.json.gz` with primary, secondary and receipt log counts and raw receipt references. Transactions with a source payload or log-index difference are also receipt-checked even when the counts agree.", "",
                  "| Transaction | Block | Etherscan / Blockscout / receipt logs |", "|---|---:|---:|"]
        for d in discrepancies:
            lines.append(f"| `{d['tx_hash']}` | {d['block']} | {d['primary_logs']} / {d['secondary_logs']} / {d['receipt_logs']} |")
        omitted = sum(max(0, d["receipt_logs"] - d["secondary_logs"]) for d in discrepancies)
        extra = sum(max(0, d["secondary_logs"] - d["receipt_logs"]) for d in discrepancies)
        primary_matches = sum(d["primary_matches_receipt"] for d in discrepancies)
        lines += ["", f"Across these disputed transactions, Blockscout omitted {omitted} receipt logs and supplied {extra} extra log entries. Etherscan matched the receipts for {primary_matches} of {len(discrepancies)} disputed transactions. Equal-count rows in this table reflect payload or index differences rather than a count gap."]
    lines += ["",
              "## Balances and destruction", "",
              f"Historical `balanceOf` was attempted for {report['historical_balances_attempted']} randomly selected Ethereum freeze logs; {report['historical_balances_available']} succeeded. Successful values are end-of-freeze-block balances, which can differ from the exact pre-log balance if another transaction in that block moved funds. Unavailable values remain blank, never zero. Tron historical balances are not supplied by the public constant-contract API.", "",
              "`DestroyedBlackFunds` amounts are decoded exactly with 6 decimals. They describe the balance destroyed immediately before that destruction call; they are not automatically the balance at the earlier freeze, because an address can receive additional funds while blacklisted. No burn amount is relabelled as an earlier freeze balance. `balance_at_freeze` is populated only by the explicitly labelled historical balance call.", "",
              "## Circle burn/clawback review", "",
              f"The verified proxy source response `{report['contract_review']['proxy_ref']}` identifies implementation `{report['contract_review']['implementation']}` (`{report['contract_review']['name']}`). Its full verified source/ABI is saved at `{report['contract_review']['implementation_ref']}`. In `contracts/v1/FiatTokenV1.sol`, `burn(uint256)` (lines 360–374) is restricted to an unblacklisted minter and subtracts from `msg.sender`'s own balance. The ABI has no `destroyBlackFunds`, `wipeBlacklistedAddress`, or clawback function. `Rescuable.rescueERC20` transfers tokens held by the token contract; it cannot debit arbitrary frozen holders. V2.2's `_setBalance` also rejects blacklisted accounts. Accordingly no direct frozen-account destruction mechanism was found in the currently verified implementation. This is a code-level conclusion about the checked implementation, not a claim about future proxy upgrades or off-chain redemption/legal processes.", "",
              "Ordinary USDC `Burn` events are minter burns, not evidence of frozen-fund seizure, and are intentionally excluded from the freeze table. V2.1 initialization transfers tokens accidentally held by the token contract to `lostAndFound` before internally blacklisting the contract itself; it is not a general clawback of frozen holders. The source snippets and the direct self-blacklist call are reproducible from the report's references.", "",
              "## Reproduction and incremental operation", "",
              "```sh", ".venv/bin/python -S scripts/freezes/fetch_freezes.py --refresh",
              ".venv/bin/python -S scripts/freezes/fetch_freezes.py --check", "```", "",
              "Only Python's standard library is required. `--check` makes no network requests and asserts byte-for-byte CSV agreement, source comparisons and receipt reconciliation, contiguous ranges, state-call evidence, and the saved count report. `--refresh` resumes unfinished snapshots, caches requests by credential-free URL/body, and then scans only blocks beyond each source/topic's completed range. Tron uses timestamps after the last completed solidified block. Fixed finalized snapshots avoid ordinary short reorganizations. A nonblocking `flock` prevents overlapping invocations; outputs/state are atomic replacements. A failed fetch leaves completed checkpoints intact and never publishes a partial replacement table. Etherscan requests are spaced at least 0.85 seconds apart (below 1.5 requests/second); HTTP 429 and transient errors back off. API keys are loaded at runtime and never included in raw metadata or error strings.", "",
              "`data/raw/freezes/state.json.gz` is the saved scan manifest. Every row references a gzipped request/response envelope, and `data/raw/freezes/check_report.json.gz` holds counts, current address sets, sample calls, and CSV hash. Ethereum `log_index` is the block-wide receipt log index; Tron uses TronGrid's transaction-local `event_index`. A unique row is identified by chain, token, transaction hash and log index. Tron addresses are Base58Check strings with their equivalent 20-byte hex also supplied; Ethereum addresses are lowercase hex. Probes from the previous collection remain under `probes/` and are not silently merged into the event table. Interrupted/bisected query responses may be cached but only manifest-listed leaves are counted.", "",
              "Development validation, including two incremental refresh outputs, CSV hashes, the overlapping-run lock check and unit-test output, is saved in `data/raw/freezes/execution_validation.json.gz`.", "",
              "## Other chains", "",
              "Stretch chains were not collected: native USDC on Arbitrum, Base, Polygon, Avalanche and Optimism; other USDT deployments; and Solana freeze-authority instructions. Their histories and blacklist sets are unknown in this output. Bridged token contracts are not interchangeable with issuer-native deployments. This table must not be presented as an all-chain inventory.", ""]
    (ROOT / "docs/FREEZES.md").write_text("\n".join(lines))
    coverage = ROOT / "docs/COVERAGE.md"
    start, end = "<!-- freezes:start -->", "<!-- freezes:end -->"
    section = (f"{start}\n## Freezes — issuer blacklist event history\n\n"
               f"- Output: `data/freezes.csv`, {report['event_rows']:,} event logs; reproducible with `scripts/freezes/fetch_freezes.py --check`. Details and dates: `docs/FREEZES.md`.\n"
               "- ETH USDT (add/remove/destroy) and ETH USDC (blacklist/unblacklist): full Etherscan histories through the documented finalized head. Blockscout full-range comparisons where available, with discrepancies resolved by independent dRPC receipts; HTTP 429 prevented completing every secondary topic. All Ethereum topics also have independent dRPC single-block log samples. See exact ranges and differences in `docs/FREEZES.md`.\n"
               "- TRX USDT (add/remove/destroy): genesis timestamp through documented solidified head; full ascending/descending TronGrid fingerprint passes agree. Same-indexer retention is a residual uncertainty; TronScan transfer totals are not accepted as blacklist counts.\n"
               "- Current sets replay transitions, with 20 random active addresses per token and up to 10 cleared addresses checked by latest contract calls. No OFAC matching is performed here.\n"
               f"- Freeze balances: {report['historical_balances_available']}/{report['historical_balances_attempted']} sampled Ethereum historical calls available. Other freeze balances are blank. Destruction amounts are burn-time token units, not earlier freeze balances or USD.\n"
               "- Not covered: USDC Arbitrum/Base/Polygon/Avalanche/Optimism; other USDT chains; Solana freeze-authority instructions.\n"
               f"{end}")
    # Lock shared document separately, preserving every other process’s section.
    with (RAW / ".coverage.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        text = coverage.read_text() if coverage.exists() else "# Coverage\n"
        if start in text:
            before, tail = text.split(start, 1)
            _, after = tail.split(end, 1)
            text = before + section + after
        else:
            text = text.rstrip() + "\n\n" + section + "\n"
        coverage.write_text(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / ".fetch.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another freezes collector/check is running; exiting without changes")
            return 0
        state = load_state()
        if args.check:
            report = outputs(state, verify=True)
        else:
            fetcher = Fetcher()
            # Complete validation of a collected generation before choosing a new
            # head after an interrupted run; this prevents endlessly moving targets.
            unpublished = state.get("heads") and state.get("published_heads") != state.get("heads")
            if state.get("pending") or not unpublished:
                collect(fetcher, state)
            rows, active, touched, _ = rebuild(state, fetcher)
            rpc_sample_checks(state, rows, fetcher)
            crosscheck(fetcher, state, active, touched)
            balances(fetcher, state, rows)
            review_contracts(fetcher, state)
            report = outputs(state)
            state["published_heads"] = state["heads"].copy()
            write_gz(STATE, state)
        print(canonical({"event_rows": report["event_rows"], "current_counts": report["current_counts"],
                         "check": "passed", "csv_sha256": report["csv_sha256"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
