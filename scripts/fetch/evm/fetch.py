#!/usr/bin/env python3
"""Resumable EVM address histories and evidence-linked present balances."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import threading
import time

from bootstrap import ADDRESS, bootstrap
from chains import ALIASES, CHAINS, CROSS_CHAINS, STABLECOINS
from client import APIError, Client, RAW, ROOT, now, read_json, save_json, acquire_chain_locks

ACTIONS = ("txlist", "txlistinternal", "tokentx")


def units(number, decimals=18):
    """Exact base-unit conversion, independent of Decimal context or float."""
    number, decimals = int(number), int(decimals)
    if not 0 <= decimals <= 255:
        raise ValueError("Invalid token decimals")
    sign = "-" if number < 0 else ""
    digits = str(abs(number)).zfill(decimals + 1)
    if not decimals:
        return sign + digits
    return sign + (digits[:-decimals] + "." + digits[-decimals:]).rstrip("0").rstrip(".")


def number(value, default=0):
    if value in (None, ""):
        return default
    if isinstance(value, str):
        digits = value[2:].lstrip("0") if value.startswith("0x") else value.lstrip("+-0")
        if len(digits) > (64 if value.startswith("0x") else 78):
            raise ValueError("Integer exceeds EVM uint256 width")
    result = int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)
    if abs(result).bit_length() > 256:
        raise ValueError("Integer exceeds EVM uint256 width")
    return result


def utc(timestamp):
    return datetime.fromtimestamp(number(timestamp), timezone.utc).isoformat().replace("+00:00", "Z")


def normalized(row, action, address, symbol, ref):
    sender = (row.get("from") or "").lower()
    recipient = (row.get("to") or row.get("contractAddress") if action == "txlist" else row.get("to") or "").lower()
    if address not in {sender, recipient}:
        return None
    direction = "self" if sender == recipient == address else "out" if sender == address else "in"
    failed = str(row.get("isError", "0")) == "1" or str(row.get("txreceipt_status", "1")) == "0"
    token = action == "tokentx"
    decimals = number(row.get("tokenDecimal"), 0) if token else 18
    asset = row.get("contractAddress", "").lower() if token else symbol
    value = number(row.get("value")) if not failed else 0
    fee = number(row.get("gasUsed")) * number(row.get("gasPrice")) if action == "txlist" and sender == address else 0
    if action == "txlist" and sender == address and row.get("fee_total_raw") is not None:
        fee = number(row["fee_total_raw"])
    # L2 explorer endpoints may expose an additional L1 data fee.
    if action == "txlist" and sender == address:
        fee += number(row.get("l1Fee"))
    result = {"hash": row.get("hash", ""), "block": number(row.get("blockNumber")), "time_utc": utc(row.get("timeStamp", 0)),
              "direction": direction, "asset": asset, "symbol": row.get("tokenSymbol", "") if token else symbol,
              "decimals": decimals, "amount": units(value, decimals), "amount_raw": str(value),
              "counterparties": sorted({a for a in (sender, recipient) if a and a != address}),
              "from": sender, "to": recipient, "fee": units(fee), "fee_raw": str(fee), "fee_asset": symbol,
              "raw_ref": ref, "kind": "erc20" if token else "internal" if action == "txlistinternal" else "normal",
              "success": not failed}
    for field in ("traceId", "logIndex", "transactionIndex", "type"):
        if field in row:
            result[field] = row[field]
    return result


def load_addresses(path, cross=True):
    result = {}
    with Path(path).open() as f:
        for row in csv.DictReader(f):
            address = (row.get("address_normalized") or row.get("address") or "").strip().lower()
            if not ADDRESS.fullmatch(address):
                continue
            chain = (row.get("chain") or "").strip().lower()
            chain = ALIASES.get(chain, chain)
            if chain not in CHAINS:
                # Preserve EVM formats listed as token tickers in upstream ledgers.
                if chain in {"usdt", "usdc", "evm", "ethereum-compatible"}:
                    chain = "eth"
                else:
                    continue
            info = result.setdefault(address, {"listed_chains": set(), "dates": set(), "input_raw_refs": set()})
            info["listed_chains"].add(chain)
            for name in ("first_listed_date", "listed_date"):
                if row.get(name):
                    info["dates"].add(row[name][:10])
            if row.get("raw_ref"):
                info["input_raw_refs"].update(ref.strip() for ref in row["raw_ref"].split(";") if ref.strip())
    # Add designation dates if a concurrent process has finished the shared ledger.
    ledger = ROOT / "data/ledger.csv"
    if ledger.exists():
        with ledger.open() as f:
            for row in csv.DictReader(f):
                address = (row.get("address_normalized") or row.get("address") or "").lower()
                if address in result and row.get("listed_date"):
                    result[address]["dates"].add(row["listed_date"][:10])
    for info in result.values():
        info["chains"] = sorted(info["listed_chains"] | (set(CROSS_CHAINS) if cross else set()))
        for k in info:
            info[k] = sorted(info[k])
    return result


class Fetcher:
    def __init__(self, client, max_pages=600):
        self.c = client
        self.max_pages = max_pages
        self.heads = {}
        self.snapshots = {}
        self.providers = {}
        self.provider_notes = {}
        self.block_cache = {}
        self.block_lock = threading.Lock()
        self.metadata = {}
        self.metadata_lock = threading.Lock()
        self.unavailable = {}

    def rpc(self, chain, method, params, **kw):
        return self.c.rpc(CHAINS[chain]["rpc"], method, params, **kw)

    def block(self, chain, height):
        key = (chain, height)
        with self.block_lock:
            cached = self.block_cache.get(key)
        if cached:
            return cached
        value, ref = self.rpc(chain, "eth_getBlockByNumber", [hex(height), False])
        if not value:
            raise APIError(f"Block {height} not returned", ref)
        with self.block_lock:
            self.block_cache[key] = value, ref
        return value, ref

    def block_at(self, chain, timestamp):
        low, high = 0, self.heads[chain]["block"]
        while low < high:
            mid = (low + high + 1) // 2
            value, _ = self.block(chain, mid)
            if number(value["timestamp"]) <= timestamp:
                low = mid
            else:
                high = mid - 1
        return low

    def explorer(self, chain, provider, action, **params):
        config = CHAINS[chain]
        if chain in self.unavailable:
            failure = self.unavailable[chain]
            raise APIError(failure["error"], failure["raw_ref"])
        if provider == "etherscan":
            return self.c.etherscan(config["id"], action, **params)
        if provider == "blockscout":
            url = config["blockscout"] + "/api"
        else:
            url = f"https://api.routescan.io/v2/network/mainnet/evm/{config['id']}/etherscan/api"
        try:
            payload, ref = self.c.request(provider, url, {"module": "account", "action": action, **params})
        except APIError as exc:
            if "429" in str(exc) and chain in self.providers:
                failure = {"provider": provider, "error": "Persistent HTTP 429 after bounded backoff; chain history circuit opened for this run", "raw_ref": exc.raw_ref}
                self.unavailable[chain] = failure
                self.providers[chain] = None
                self.provider_notes[chain].append(failure)
            raise
        if isinstance(payload, dict) and isinstance(payload.get("result"), list):
            return payload["result"], ref
        raise APIError(str(payload)[:220], ref)

    def setup(self, chain, addresses):
        config = CHAINS[chain]
        value, head_ref = self.rpc(chain, "eth_blockNumber", [], fresh=True)
        # A finalized-ish fixed block avoids mixed-time balances and explorer races.
        height = max(0, number(value) - 64)
        block, block_ref = self.block(chain, height)
        self.heads[chain] = {"block": height, "time_utc": utc(block["timestamp"]), "raw_ref": head_ref, "block_raw_ref": block_ref}
        probe = "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b"
        capability_path = RAW / f"reports/capability_{chain}.json.gz"
        capability = read_json(capability_path) if capability_path.exists() else None
        if capability and capability["provider"] is None and getattr(self, "refresh", False):
            capability = None  # Retry previously unavailable providers on refresh.
        notes = capability["notes"] if capability else []
        provider = capability["provider"] if capability else None
        for candidate in (() if capability else ("etherscan", "blockscout_v2", "blockscout", "routescan")):
            if not config.get("blockscout" if candidate == "blockscout_v2" else candidate):
                continue
            try:
                if candidate == "blockscout_v2":
                    payload, ref = self.c.request("blockscout", config["blockscout"] + f"/api/v2/addresses/{probe}/transactions")
                    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                        raise APIError(str(payload)[:220], ref)
                else:
                    self.explorer(chain, candidate, "txlist", address=probe, startblock=0, endblock=height, page=1, offset=1, sort="asc")
                provider = candidate
                break
            except APIError as exc:
                notes.append({"provider": candidate, "error": str(exc), "raw_ref": exc.raw_ref})
        save_json(capability_path, {"provider": provider, "notes": notes, "checked_at": now(), "chain": chain})
        self.providers[chain] = provider
        self.provider_notes[chain] = notes
        print(json.dumps({"chain": chain, "head": height, "provider": provider, "addresses": len(addresses)}), flush=True)
        snapshot_group = 3 if chain in {"op", "base", "arb", "polygon"} else 20
        for start in range(0, len(addresses), snapshot_group):
            group = addresses[start:start + snapshot_group]
            calls = [(method, [address, hex(height)]) for address in group for method in ("eth_getBalance", "eth_getTransactionCount", "eth_getCode")]
            try:
                values, ref = self.c.batch(config["rpc"], calls)
                for i, address in enumerate(group):
                    selected = values[i * 3:i * 3 + 3]
                    self.snapshots[chain, address] = {"balance": selected[0][0], "nonce": selected[1][0], "code": selected[2][0],
                                                      "errors": [error for _, error in selected if error], "raw_ref": f"{ref}#/response", "batch_index": i * 3}
            except APIError as exc:
                for address in group:
                    self.snapshots[chain, address] = {"errors": [str(exc)], "raw_ref": exc.raw_ref}

    def history(self, chain, address, action, low, high, provider, budget=None):
        if provider == "blockscout_v2":
            return self.history_v2(chain, address, action, low, high, budget)
        cursor, pages, target = low, 0, high
        output, refs = [], []
        limit = self.max_pages if budget is None else budget
        while cursor <= high:
            if pages >= limit:
                return output, refs, {"action": action, "from_block": cursor, "to_block": high, "reason": f"Per-address page budget {limit} reached"}
            try:
                rows, ref = self.explorer(chain, provider, action, address=address, startblock=cursor, endblock=target, page=1, offset=10000, sort="asc")
            except APIError as exc:
                pages += 1
                if cursor < target and any(word in str(exc).lower() for word in ("timeout", "timed out", "smaller result", "query size")):
                    target = (cursor + target) // 2
                    continue
                return output, refs, {"action": action, "from_block": cursor, "to_block": high, "reason": str(exc), "raw_ref": exc.raw_ref}
            pages += 1
            refs.append(ref)
            # Free-tier responses can silently clamp offset=10000 to 1000.
            # Treat either full size as a capped window and advance by block.
            if len(rows) < 1000:
                output.extend((r, f"{ref}#/response/result/{i}") for i, r in enumerate(rows))
                cursor, target = target + 1, high
                continue
            boundary = number(rows[-1]["blockNumber"])
            if boundary <= cursor:
                # Multiple pages within this one block are still below the
                # explorer's 10k window. Do not mistake the 1k cap for 10k logs.
                block_complete = False
                for page in range(1, 11):
                    if pages >= limit:
                        break
                    try:
                        block_rows, block_ref = self.explorer(chain, provider, action, address=address, startblock=cursor, endblock=cursor, page=page, offset=1000, sort="asc")
                    except APIError as exc:
                        return output, refs, {"action": action, "from_block": cursor, "to_block": high, "reason": str(exc), "raw_ref": exc.raw_ref}
                    pages += 1
                    refs.append(block_ref)
                    output.extend((r, f"{block_ref}#/response/result/{i}") for i, r in enumerate(block_rows))
                    if len(block_rows) < 1000:
                        block_complete = True
                        break
                if not block_complete:
                    return output, refs, {"action": action, "from_block": cursor, "to_block": high, "reason": "Single block reaches the 10000-record result window or page budget; block-local pagination cannot establish completeness", "raw_ref": ref}
                cursor += 1
                target = high
                continue
            # The boundary block may be truncated: refetch it from the beginning.
            output.extend((r, f"{ref}#/response/result/{i}") for i, r in enumerate(rows) if number(r["blockNumber"]) < boundary)
            cursor = boundary
        return output, refs, None

    def history_v2(self, chain, address, action, low, high, budget=None):
        endpoint = {"txlist": "transactions", "txlistinternal": "internal-transactions", "tokentx": "token-transfers"}[action]
        url = CHAINS[chain]["blockscout"] + f"/api/v2/addresses/{address}/{endpoint}"
        params = {"type": "ERC-20"} if action == "tokentx" else {}
        output, refs, cursors = [], [], set()
        limit = self.max_pages if budget is None else budget
        for page in range(limit):
            try:
                payload, ref = self.c.request("blockscout", url, params, fresh=bool(low > 0 and page == 0))
                if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                    raise APIError(str(payload)[:220], ref)
            except APIError as exc:
                return output, refs, {"action": action, "from_block": low, "to_block": high, "reason": str(exc), "raw_ref": exc.raw_ref}
            refs.append(ref)
            crossed_low = False
            for i, item in enumerate(payload["items"]):
                if item.get("block_number") is None:
                    continue  # Pending/unconfirmed records are outside fixed-head coverage.
                block = number(item.get("block_number"))
                if block > high:
                    continue
                if block < low:
                    crossed_low = True
                    continue
                def addr(value):
                    return (value or {}).get("hash", "") if isinstance(value, (dict, type(None))) else value
                timestamp = item.get("timestamp")
                if not timestamp:
                    return output, refs, {"action": action, "from_block": low, "to_block": high, "reason": "Blockscout v2 item has no timestamp", "raw_ref": f"{ref}#/response/items/{i}"}
                row = {"blockNumber": block, "hash": item.get("hash") or item.get("transaction_hash"), "timeStamp": int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()),
                       "from": addr(item.get("from")), "to": addr(item.get("to")) or addr(item.get("created_contract")), "value": item.get("value", 0),
                       "gasUsed": item.get("gas_used", 0), "gasPrice": item.get("gas_price", 0),
                       "isError": "1" if item.get("success") is False or item.get("error") or item.get("status") in {"error", "failed", "reverted"} else "0"}
                if action == "txlist":
                    fee = item.get("fee") or {}
                    if fee.get("value") is not None:
                        row["fee_total_raw"] = fee["value"]
                    if item.get("l1_fee") is not None:
                        row["l1Fee"] = item["l1_fee"]
                elif action == "txlistinternal":
                    row["traceId"] = item.get("index", item.get("transaction_index", i))
                    row["type"] = item.get("type", "")
                else:
                    token, total = item.get("token") or {}, item.get("total") or {}
                    if token.get("type") != "ERC-20":
                        continue
                    if total.get("value") is None:
                        return output, refs, {"action": action, "from_block": low, "to_block": high, "reason": "ERC20 item has no transfer value", "raw_ref": f"{ref}#/response/items/{i}"}
                    row.update({"contractAddress": token.get("address_hash") or token.get("address"), "tokenSymbol": token.get("symbol") or "", "tokenDecimal": token.get("decimals") or total.get("decimals") or 0,
                                "value": total["value"], "logIndex": item.get("log_index", i)})
                output.append((row, f"{ref}#/response/items/{i}"))
            cursor = payload.get("next_page_params")
            if not cursor or crossed_low:
                return output, refs, None
            identity = json.dumps(cursor, sort_keys=True)
            if identity in cursors:
                return output, refs, {"action": action, "from_block": low, "to_block": high, "reason": "Blockscout v2 repeated pagination cursor", "raw_ref": ref}
            cursors.add(identity)
            params.update(cursor)
        return output, refs, {"action": action, "from_block": low, "to_block": high, "reason": f"Blockscout v2 page budget {limit} reached"}

    def balances(self, chain, address, txs, snapshot, head):
        config = CHAINS[chain]
        balances, errors = [], []
        if snapshot.get("balance") is not None:
            balances.append({"asset": config["symbol"], "symbol": config["symbol"], "decimals": 18, "amount": units(number(snapshot["balance"])),
                             "amount_raw": str(number(snapshot["balance"])), "block": head, "source": config["rpc"],
                             "raw_ref": snapshot["raw_ref"], "rpc_response_id": snapshot["batch_index"]})
        elif chain == "etc":
            # Blockscout's RPC bridge can report "Balance not found" for an
            # unindexed account while its native address API reports a balance.
            try:
                url = config["blockscout"] + f"/api/v2/addresses/{address}"
                value, ref = self.c.request("blockscout", url, fresh=True)
                if isinstance(value, dict) and value.get("coin_balance") is not None:
                    balances.append({"asset": config["symbol"], "symbol": config["symbol"], "decimals": 18, "amount": units(number(value["coin_balance"])),
                                     "amount_raw": str(number(value["coin_balance"])), "block": value.get("block_number_balance_updated_at"), "source": url,
                                     "raw_ref": ref + "#/response/coin_balance", "observed_at": now(), "note": "Blockscout-reported last balance update block; may differ from history end."})
            except APIError as exc:
                errors.append({"asset": config["symbol"], "reason": str(exc), "raw_ref": exc.raw_ref})
        assets = dict(STABLECOINS.get(chain, {}))
        metadata = {}
        for tx in txs:
            if tx.get("kind") == "erc20" and ADDRESS.fullmatch(tx["asset"]):
                assets[tx["asset"]] = (tx["symbol"], tx["decimals"])
                if tx.get("raw_ref"):
                    metadata[tx["asset"]] = tx["raw_ref"]
        for asset in assets:
            if asset in metadata:
                continue
            key = (chain, asset, head)
            with self.metadata_lock:
                if key not in self.metadata:
                    ref = None
                    try:
                        value, ref = self.rpc(chain, "eth_call", [{"to": asset, "data": "0x313ce567"}, hex(head)])
                        self.metadata[key] = (number(value), ref) if value and value != "0x" else (None, ref)
                    except (APIError, ValueError) as exc:
                        self.metadata[key] = (None, getattr(exc, "raw_ref", ref))
                decimals, ref = self.metadata[key]
            metadata[asset] = ref
            if decimals is not None and 0 <= decimals <= 255:
                assets[asset] = (assets[asset][0], decimals)
            else:
                errors.append({"asset": asset, "reason": "Could not verify configured token decimals", "raw_ref": ref})
        items = sorted(assets.items())
        group_size = 10 if chain in {"op", "base", "arb", "polygon"} else 40
        for start in range(0, len(items), group_size):
            group = items[start:start + group_size]
            calls = [("eth_call", [{"to": asset, "data": "0x70a08231" + address[2:].zfill(64)}, hex(head)]) for asset, _ in group]
            try:
                values, ref = self.c.batch(config["rpc"], calls)
                for i, ((asset, (symbol, decimals)), (value, error)) in enumerate(zip(group, values)):
                    if error or not isinstance(value, str) or len(value) != 66 or not value.startswith("0x"):
                        errors.append({"asset": asset, "reason": error or "balanceOf did not return a single ABI uint256 word", "raw_ref": ref, "rpc_response_id": i})
                    else:
                        balances.append({"asset": asset, "symbol": symbol, "decimals": decimals, "amount": units(number(value), decimals), "amount_raw": str(number(value)),
                                         "block": head, "source": config["rpc"], "raw_ref": ref, "rpc_response_id": i, "metadata_raw_ref": metadata.get(asset)})
            except APIError as exc:
                errors.append({"assets": [asset for asset, _ in group], "reason": str(exc), "raw_ref": exc.raw_ref})
        return balances, errors

    def fetch_address(self, chain, address, info, refresh=False):
        path = ROOT / f"data/timelines/{chain}/{address}.json.gz"
        previous = read_json(path) if path.exists() else None
        if previous:
            previous["input_raw_refs"] = info["input_raw_refs"]
            previous["designation_dates"] = info["dates"]
            previous["listed_chains"] = info["listed_chains"]
        config = CHAINS[chain]
        head = self.heads[chain]
        snapshot = self.snapshots[chain, address]
        if chain == "eth" and snapshot.get("code") is None:
            code, code_ref = self.rpc(chain, "eth_getCode", [address, hex(head["block"])])
            snapshot = {**snapshot, "code": code, "code_raw_ref": code_ref}
        provider = self.providers[chain]
        relation = "OFAC-listed chain" if chain in info["listed_chains"] else "same address, other chain"
        document = {"chain": chain, "address": address, "fetched_at": now(), "source": {"history": provider, "balance": config["rpc"]},
                    "listing_relation": relation, "listed_chains": info["listed_chains"], "designation_dates": info["dates"], "input_raw_refs": info["input_raw_refs"],
                    "contract": snapshot["code"] != "0x" if snapshot.get("code") is not None else None, "contract_raw_ref": snapshot.get("code_raw_ref", snapshot.get("raw_ref")),
                    "nonce_now": number(snapshot["nonce"]) if snapshot.get("nonce") is not None else None, "txs": [],
                    "coverage": {"from_block": 0, "to_block": head["block"], "to_time": head["time_utc"], "complete": False,
                                 "notes": [], "missing_ranges": [], "raw_refs": []}, "balance_now": [], "balance_errors": []}
        coverage = document["coverage"]
        if previous and previous.get("fetch_schema_version") != 2:
            # Version 1 assumed the requested offset was the effective cap.
            # Reuse its raw pages, but re-establish block-range completeness.
            previous["coverage"]["complete"] = False
            previous["coverage"]["actions"] = {name: {**state, "complete": False, "covered_to_block": -1} for name, state in previous["coverage"].get("actions", {}).items()}
        document["fetch_schema_version"] = 2
        if previous and previous.get("tornado_pool") and previous.get("log_coverage", {}).get("complete") and previous["coverage"].get("daily_balances_complete") and not refresh:
            document = previous
            document["fetched_at"] = now()
            pool = document["pool_interface"]
            assets = [{"kind": "erc20", "asset": pool["asset"], "symbol": pool["symbol"], "decimals": pool["decimals"]}] if pool["asset"] != "ETH" else []
            document["balance_now"], document["balance_errors"] = self.balances(chain, address, assets, snapshot, head["block"])
            document["balance_observation"] = head
            if document["coverage"]["to_block"] != head["block"]:
                document["pool_validation"]["conclusive"] = False
                document["pool_validation"]["match"] = False
            # Balance history is refreshed only for newly completed calendar days.
            from tornado import daily_balances
            document["daily_balance"], document["daily_balance_errors"] = daily_balances(self, address, pool, previous)
            save_json(path, document)
            return document
        if previous and previous["coverage"].get("complete") and not refresh:
            # Completed histories are reused; only chain head and present balances are checked.
            document = previous
            document["fetched_at"] = now()
            document["balance_now"], document["balance_errors"] = self.balances(chain, address, document["txs"], snapshot, head["block"])
            document["balance_observation"] = head
            save_json(path, document)
            return document
        if previous and not refresh:
            # Resume the same immutable range, using cached completed pages.
            history_block = previous["coverage"]["to_block"]
            coverage["to_block"] = history_block
            coverage["to_time"] = previous["coverage"].get("to_time")
        else:
            history_block = head["block"]
        if snapshot.get("errors"):
            coverage["notes"].append({"snapshot_errors": snapshot["errors"], "raw_ref": snapshot.get("raw_ref")})
        if not provider:
            coverage["notes"].append("No accessible history index: zero current balance/nonce does not exclude earlier incoming transfers or token activity.")
            coverage["missing_ranges"].append({"actions": list(ACTIONS), "from_block": 0, "to_block": head["block"], "reason": "No available public history provider", "provider_errors": self.provider_notes[chain]})
        else:
            # Pool contracts have a dedicated log/balance path, never txlist.
            if document["contract"] and chain == "eth":
                from tornado import maybe_pool, fetch_pool
                pool = maybe_pool(self, chain, address, history_block)
                if pool:
                    return fetch_pool(self, document, pool, snapshot, path, previous, refresh)
            txs = []
            for action in ACTIONS:
                old_state = (previous or {}).get("coverage", {}).get("actions", {}).get(action, {})
                low = old_state.get("covered_to_block", old_state.get("to_block", -1) if old_state.get("complete") else -1) + 1 if refresh else 0
                if refresh and previous and previous["coverage"].get("complete"):
                    low = previous["coverage"]["to_block"] + 1
                if previous and refresh:
                    txs.extend(tx for tx in previous["txs"] if tx["kind"] == {"txlist": "normal", "txlistinternal": "internal", "tokentx": "erc20"}[action])
                rows, refs, missing = self.history(chain, address, action, low, history_block, provider)
                grouped_rows = [(row, ref, "history") for row, ref in rows]
                coverage["raw_refs"].extend(refs)
                coverage.setdefault("actions", {})[action] = {"from_block": 0, "to_block": history_block, "covered_to_block": missing["from_block"] - 1 if missing else history_block, "complete": missing is None, "raw_refs": old_state.get("raw_refs", []) + refs if refresh else refs}
                if missing:
                    coverage["missing_ranges"].append(missing)
                    # Explicit required windows, using real block timestamps.
                    windows = [(datetime.fromisoformat(d).replace(tzinfo=timezone.utc) - timedelta(days=60), datetime.fromisoformat(d).replace(tzinfo=timezone.utc) + timedelta(days=400), d) for d in info["dates"]]
                    end = datetime.fromisoformat(coverage["to_time"].replace("Z", "+00:00"))
                    windows.append((end - timedelta(days=90), end, "latest90d"))
                    for start_date, end_date, label in windows:
                        try:
                            start_block = min(history_block, self.block_at(chain, int(start_date.timestamp())))
                            end_block = min(history_block, self.block_at(chain, int(end_date.timestamp())))
                            window_rows, window_refs, window_gap = self.history(chain, address, action, start_block, end_block, provider, budget=self.max_pages)
                            grouped_rows.extend((row, ref, f"window:{label}") for row, ref in window_rows)
                            coverage.setdefault("priority_windows", []).append({"action": action, "label": label, "from_block": start_block, "to_block": end_block, "complete": window_gap is None, "raw_refs": window_refs, "missing": window_gap})
                        except (APIError, ValueError) as exc:
                            coverage.setdefault("priority_windows", []).append({"action": action, "label": label, "complete": False, "reason": str(exc), "raw_ref": getattr(exc, "raw_ref", None)})
                token_occurrences = Counter()
                for row, ref, acquisition_group in grouped_rows:
                    try:
                        tx = normalized(row, action, address, config["symbol"], ref)
                        if tx:
                            if action == "tokentx" and "logIndex" not in tx:
                                fingerprint = (acquisition_group, tx["hash"], tx["asset"], tx["from"], tx["to"], tx["amount_raw"])
                                tx["transfer_ordinal"] = token_occurrences[fingerprint]
                                token_occurrences[fingerprint] += 1
                            txs.append(tx)
                    except (ValueError, TypeError) as exc:
                        coverage["notes"].append({"normalization_error": str(exc), "raw_ref": ref})
            # Deduplicate records fetched again in priority windows, retaining identical
            # distinct token logs inside the original response when logIndex is absent.
            unique = {}
            for tx in txs:
                key = (tx["kind"], tx["hash"], tx.get("traceId"), tx.get("logIndex"), tx["asset"], tx["from"], tx["to"], tx["amount_raw"], tx.get("transfer_ordinal", 0))
                unique[key] = tx
            document["txs"] = sorted(unique.values(), key=lambda tx: (tx["block"], number(tx.get("transactionIndex")), tx["kind"], str(tx.get("traceId", ""))))
            coverage["complete"] = not coverage["missing_ranges"] and not any("normalization_error" in note for note in coverage["notes"] if isinstance(note, dict))
        document["balance_now"], document["balance_errors"] = self.balances(chain, address, document["txs"], snapshot, head["block"])
        document["balance_observation"] = head
        document["coverage"]["balances_complete"] = bool(document["balance_now"]) and not document["balance_errors"] and snapshot.get("balance") is not None
        document["activity_found"] = bool(document["txs"] or number(snapshot.get("balance")) or number(snapshot.get("nonce")) or document["contract"] or any(number(int(b["amount_raw"])) for b in document["balance_now"]))
        save_json(path, document)
        return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addresses", type=Path)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--chains", default=",".join(CHAINS))
    parser.add_argument("--no-cross-chain", action="store_true")
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--max-pages", type=int, default=600)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--report-name", default="fetch_run", help="Separate report for disjoint chain runs")
    parser.add_argument("--check", action="store_true", help="Offline evidence/schema/balance validation")
    args = parser.parse_args()
    if not args.report_name.replace("_", "").replace("-", "").isalnum():
        parser.error("report-name must contain only letters, digits, underscore or hyphen")
    if args.check:
        from validate import validate
        return validate()
    c = Client()
    address_path = args.addresses
    if args.bootstrap or (not address_path and not (ROOT / "data/addresses.csv").exists() and not (ROOT / "data/bootstrap/fetch_evm.csv").exists()):
        address_path = bootstrap(c)
    if not address_path:
        address_path = ROOT / ("data/addresses.csv" if (ROOT / "data/addresses.csv").exists() else "data/bootstrap/fetch_evm.csv")
    addresses = load_addresses(address_path, not args.no_cross_chain)
    if args.limit:
        addresses = dict(list(addresses.items())[:args.limit])
    selected = [ch for ch in args.chains.split(",") if ch in CHAINS]
    locks = acquire_chain_locks(selected)
    fetcher = Fetcher(c, args.max_pages)
    fetcher.refresh = args.refresh
    report = {"started_at": now(), "addresses_file": str(address_path), "distinct_addresses": len(addresses), "chains": {}, "failures": []}
    for chain in selected:
        group = sorted(a for a, info in addresses.items() if chain in info["chains"])
        if not group:
            continue
        try:
            fetcher.setup(chain, group)
        except APIError as exc:
            report["failures"].append({"chain": chain, "reason": str(exc), "raw_ref": exc.raw_ref, "addresses": group})
            print(json.dumps(report["failures"][-1]), flush=True)
            continue
        counts = Counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            jobs = {pool.submit(fetcher.fetch_address, chain, address, addresses[address], args.refresh): address for address in group}
            for future in as_completed(jobs):
                address = jobs[future]
                try:
                    doc = future.result()
                    counts["timelines"] += 1
                    counts["complete"] += int(doc["coverage"]["complete"])
                    counts["active"] += int(doc.get("activity_found", bool(doc["txs"])))
                    counts["transactions"] += len(doc["txs"])
                    print(json.dumps({"chain": chain, "address": address, "txs": len(doc["txs"]), "complete": doc["coverage"]["complete"], "pool": doc.get("tornado_pool", False), "done": counts["timelines"], "total": len(group)}), flush=True)
                except Exception as exc:
                    failure = {"chain": chain, "address": address, "reason": f"{type(exc).__name__}: {exc}", "raw_ref": getattr(exc, "raw_ref", None)}
                    report["failures"].append(failure)
                    print(json.dumps(failure), flush=True)
                    failed_path = ROOT / f"data/timelines/{chain}/{address}.json.gz"
                    if failed_path.exists():
                        failed_doc = read_json(failed_path)
                        failed_doc["last_fetch_error"] = failure
                    else:
                        failed_doc = {"chain": chain, "address": address, "fetched_at": now(), "fetch_schema_version": 2,
                                      "source": {"history": fetcher.providers[chain], "balance": CHAINS[chain]["rpc"]},
                                      "listing_relation": "OFAC-listed chain" if chain in addresses[address]["listed_chains"] else "same address, other chain",
                                      "listed_chains": addresses[address]["listed_chains"], "designation_dates": addresses[address]["dates"],
                                      "contract": bool(fetcher.snapshots.get((chain, address), {}).get("code") not in (None, "0x")),
                                      "coverage": {"from_block": 0, "to_block": fetcher.heads[chain]["block"], "to_time": fetcher.heads[chain]["time_utc"], "complete": False,
                                                   "notes": [failure], "missing_ranges": [{"from_block": 0, "to_block": fetcher.heads[chain]["block"], "reason": failure["reason"], "raw_ref": failure["raw_ref"]}]},
                                      "txs": [], "balance_now": [], "balance_errors": [failure]}
                    save_json(failed_path, failed_doc)
                report["chains"][chain] = dict(counts)
                report["updated_at"] = now()
                report["network_calls"] = c.network_calls
                save_json(RAW / f"reports/{args.report_name}.json.gz", report)
    report["finished_at"] = now()
    save_json(RAW / f"reports/{args.report_name}.json.gz", report)
    print(json.dumps(report), flush=True)
    for handle in locks:
        handle.close()
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
