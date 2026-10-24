"""Pool detection, direct daily archive balances, and Deposit/Withdrawal logs.

Pool event flows and direct balance snapshots are distinct evidence streams.
No individual pool deposits/withdrawals are requested through txlist.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import json
import threading

from chains import CHAINS
from client import APIError, RAW, now, read_json, save_json
from fetch import number, units, utc

ARCHIVE = "https://rpc.mevblocker.io"
_daily_lock = threading.Lock()
_daily = None
_topic_lock = threading.Lock()
_topics = {}


def evm_failure(error):
    return any(text in str(error).lower() for text in ("revert", "invalidfeopcode", "invalid opcode", "invalid jump"))


def signature(fetcher, value):
    with _topic_lock:
        if value not in _topics:
            result, ref = fetcher.c.rpc("https://ethereum-rpc.publicnode.com", "web3_sha3", ["0x" + value.encode().hex()])
            _topics[value] = result, ref
        return _topics[value]


def maybe_pool(fetcher, chain, address, head):
    denom_selector, signature_ref = signature(fetcher, "denomination()")
    try:
        denom, ref = fetcher.rpc(chain, "eth_call", [{"to": address, "data": denom_selector[:10]}, hex(head)])
        if not denom or len(denom) != 66 or number(denom) <= 0:
            return None
        # Require independent pool interface fields rather than a label guess.
        token_sig, _ = signature(fetcher, "token()")
        index_sig, _ = signature(fetcher, "nextIndex()")
        index, index_ref = fetcher.rpc(chain, "eth_call", [{"to": address, "data": index_sig[:10]}, hex(head)])
        if len(index) != 66:
            return None
        try:
            token, token_ref = fetcher.rpc(chain, "eth_call", [{"to": address, "data": token_sig[:10]}, hex(head)])
            if len(token) != 66:
                return None
            token = "0x" + token[-40:]
        except APIError as exc:
            # ETHTornado does not implement token(); ERC20Tornado does.
            if not evm_failure(exc):
                raise
            token, token_ref = "0x" + "0" * 40, exc.raw_ref
        decimals, symbol = 18, "ETH"
        if int(token, 16):
            decimal_sig, _ = signature(fetcher, "decimals()")
            dec, dec_ref = fetcher.rpc(chain, "eth_call", [{"to": token, "data": decimal_sig[:10]}, hex(head)])
            decimals, symbol = number(dec), token
        else:
            dec_ref = None
        return {"denomination_raw": str(number(denom)), "token": token, "asset": token if int(token, 16) else "ETH", "decimals": decimals,
                "symbol": symbol, "next_index": number(index), "raw_refs": [ref, token_ref, index_ref, signature_ref, dec_ref]}
    except APIError as exc:
        if evm_failure(exc):
            return None
        raise  # A transport failure must never route a possible pool to txlist.
    except ValueError:
        return None


def daily_blocks(fetcher):
    """One observed block per UTC day, shared by all pools (not day-end claims)."""
    global _daily
    with _daily_lock:
        if _daily is not None:
            return _daily
        path = RAW / "reports/daily_blocks.json.gz"
        saved = read_json(path) if path.exists() else {"blocks": [], "errors": []}
        blocks = {r["date"]: r for r in saved["blocks"]}
        last_time = datetime.fromisoformat(fetcher.heads["eth"]["time_utc"].replace("Z", "+00:00"))
        errors = []
        first = datetime(2019, 1, 1, tzinfo=timezone.utc)
        # A sparse block grid supplies roughly daily observations. Missing UTC
        # dates are filled by interpolation between *observed* block times.
        # Store the actual timestamp, never an invented midnight or day-end.
        if not blocks:
            start = fetcher.block_at("eth", int(first.timestamp()))
            merge = 15537394
            heights = list(range(start, min(merge, fetcher.heads["eth"]["block"]), 6500))
            heights += list(range(merge, fetcher.heads["eth"]["block"], 7200))
        else:
            heights = []

        def observe(heights):
            for start in range(0, len(heights), 40):
                group = heights[start:start + 40]
                try:
                    results, ref = fetcher.c.batch(ARCHIVE, [("eth_getBlockByNumber", [hex(h), False]) for h in group])
                    for i, ((value, error), height) in enumerate(zip(results, group)):
                        if error or value is None:
                            errors.append({"block": height, "reason": error or "Block not returned", "raw_ref": ref})
                            continue
                        timestamp = number(value["timestamp"])
                        key = utc(timestamp)[:10]
                        if first.date().isoformat() <= key < last_time.date().isoformat():
                            blocks[key] = {"date": key, "target_time_utc": utc(timestamp), "timestamp": timestamp, "block": height, "raw_ref": ref, "rpc_response_id": i}
                except APIError as exc:
                    errors.append({"from_block": group[0], "to_block": group[-1], "reason": str(exc), "raw_ref": exc.raw_ref})
                if start % 400 == 0:
                    save_json(path, {"blocks": sorted(blocks.values(), key=lambda x: x["date"]), "errors": errors})
                    print(json.dumps({"tornado_daily_block_dates": len(blocks), "errors": len(errors)}), flush=True)

        observe(heights)
        import bisect
        for attempt in range(3):
            observed = sorted(blocks.values(), key=lambda x: x["timestamp"])
            if not observed:
                raise APIError("No daily block observations available")
            times = [r["timestamp"] for r in observed]
            extra = []
            current = first
            while current.date() < last_time.date():
                key = current.strftime("%Y-%m-%d")
                if key not in blocks:
                    target = int((current + timedelta(hours=12)).timestamp())
                    pos = bisect.bisect_left(times, target)
                    if 0 < pos < len(observed):
                        left, right = observed[pos - 1], observed[pos]
                        guess = left["block"] + (target - left["timestamp"]) * (right["block"] - left["block"]) // (right["timestamp"] - left["timestamp"])
                    else:
                        guess = fetcher.block_at("eth", target)
                    extra.append(guess)
                current += timedelta(days=1)
            if not extra:
                break
            observe(extra)
        current = first
        while current.date() < last_time.date():
            key = current.strftime("%Y-%m-%d")
            if key not in blocks:
                errors.append({"date": key, "reason": "No observed block on this UTC date"})
            current += timedelta(days=1)
        _daily = {"blocks": sorted(blocks.values(), key=lambda x: x["date"]), "errors": errors}
        save_json(path, _daily)
        return _daily


def full_logs(fetcher, address, low, high, topics, max_requests=600, extra_topics=None):
    """Split oversized result ranges; keep exact completed/missing block ranges."""
    pending = [(low, high)]
    completed, missing, logs = [], [], []
    requests = 0
    while pending:
        start, end = pending.pop()
        if start > end:
            continue
        if requests >= max_requests:
            missing.extend({"from_block": a, "to_block": b, "reason": "Pool log request budget reached"} for a, b in [(start, end), *pending])
            break
        requests += 1
        try:
            result, ref = fetcher.c.rpc(ARCHIVE, "eth_getLogs", [{"address": address, "fromBlock": hex(start), "toBlock": hex(end), "topics": [topics] + list(extra_topics or [])}])
            if not isinstance(result, list):
                raise APIError("Expected a log array", ref)
            completed.append({"from_block": start, "to_block": end, "raw_ref": ref})
            logs.extend({**row, "raw_ref": f"{ref}#/response/result/{i}"} for i, row in enumerate(result) if not row.get("removed"))
        except APIError as exc:
            text = str(exc).lower()
            if start < end and any(word in text for word in ("size", "limit", "range", "timeout", "timed out")):
                mid = (start + end) // 2
                pending.extend([(mid + 1, end), (start, mid)])
            else:
                missing.append({"from_block": start, "to_block": end, "reason": str(exc), "raw_ref": exc.raw_ref})
    return sorted(logs, key=lambda r: (number(r["blockNumber"]), number(r["logIndex"]))), completed, missing


def daily_balances(fetcher, address, pool, previous=None):
    daily = daily_blocks(fetcher)
    observations = {r["date"]: r for r in (previous or {}).get("daily_balance", [])}
    pending = [r for r in daily["blocks"] if r["date"] not in observations]
    errors = list(daily["errors"])
    for start in range(0, len(pending), 40):
        group = pending[start:start + 40]
        calls = []
        for row in group:
            calls.append(("eth_getBalance", [address, hex(row["block"])]))
            if pool["asset"] != "ETH":
                calls.append(("eth_call", [{"to": pool["token"], "data": "0x70a08231" + address[2:].zfill(64)}, hex(row["block"])]))
        try:
            results, ref = fetcher.c.batch(ARCHIVE, calls)
        except APIError as exc:
            errors.append({"dates": [r["date"] for r in group], "reason": str(exc), "raw_ref": exc.raw_ref})
            continue
        stride = 2 if pool["asset"] != "ETH" else 1
        for i, row in enumerate(group):
            balance, error = results[i * stride]
            assets = []
            if balance is not None and not error:
                assets.append({"asset": "ETH", "decimals": 18, "amount": units(number(balance)), "amount_raw": str(number(balance)), "rpc_response_id": i * stride})
            if stride == 2:
                token_balance, token_error = results[i * stride + 1]
                # Empty code/return before token deployment has no token balance to observe.
                if token_balance and token_balance != "0x" and not token_error:
                    assets.append({"asset": pool["token"], "decimals": pool["decimals"], "amount": units(number(token_balance), pool["decimals"]), "amount_raw": str(number(token_balance)), "rpc_response_id": i * stride + 1})
                elif token_error:
                    errors.append({"date": row["date"], "asset": pool["token"], "reason": token_error, "raw_ref": ref})
            if error or not assets:
                errors.append({"date": row["date"], "reason": error or "Missing native balance", "raw_ref": ref})
            else:
                observations[row["date"]] = {"date": row["date"], "time_utc": row["target_time_utc"], "block": row["block"], "assets": assets, "source": ARCHIVE,
                                             "raw_ref": ref, "block_raw_ref": row["raw_ref"]}
    return sorted(observations.values(), key=lambda x: x["date"]), errors


def fetch_pool(fetcher, document, pool, snapshot, path, previous, refresh):
    address = document["address"]
    head = document["coverage"]["to_block"]
    balance_head = fetcher.heads["eth"]["block"]
    document["tornado_pool"] = True
    document["pool_interface"] = pool
    document["source"]["history"] = {"method": "eth_getLogs Deposit/Withdrawal", "url": ARCHIVE}
    document["coverage"]["notes"].append("Pool event history replaces txlist; event flows exclude unsolicited donations, other token transfers, and contract administration. Direct archive balances are measured independently.")
    deposit, deposit_ref = signature(fetcher, "Deposit(bytes32,uint32,uint256)")
    withdrawal, withdrawal_ref = signature(fetcher, "Withdrawal(address,bytes32,address,uint256)")
    low = previous["coverage"]["to_block"] + 1 if refresh and previous and previous.get("log_coverage", {}).get("complete") else 0
    logs, completed, missing = full_logs(fetcher, address, low, head, [deposit, withdrawal])
    if low:
        logs = (previous or {}).get("pool_logs", []) + logs
    document["pool_logs"] = logs
    document["log_coverage"] = {"from_block": 0, "to_block": head, "complete": not missing, "completed_ranges": completed, "missing_ranges": missing,
                                "topic_raw_refs": [deposit_ref, withdrawal_ref]}
    document["daily_balance"], document["daily_balance_errors"] = daily_balances(fetcher, address, pool, previous)
    # Withdrawal times are bounded by adjacent sampled blocks; deposits carry
    # the exact timestamp in their event data.
    daily = document["daily_balance"]
    import bisect
    heights = [r["block"] for r in daily]
    txs = []
    prior_times = {(tx["hash"], number(tx.get("logIndex", 0))): {k: tx[k] for k in ("time_utc", "time_raw_ref", "time_precision") if k in tx}
                   for tx in (previous or {}).get("txs", []) if tx.get("time_utc")}
    denomination = number(pool["denomination_raw"])
    for event in logs:
        topic = event["topics"][0].lower()
        height = number(event["blockNumber"])
        pos = bisect.bisect_left(heights, height)
        upper_time = daily[pos]["time_utc"] if pos < len(daily) else fetcher.heads["eth"]["time_utc"]
        lower_time = daily[pos - 1]["time_utc"] if pos else None
        is_deposit = topic == deposit.lower()
        words = [event["data"][i:i + 64] for i in range(2, len(event["data"]), 64)]
        counterparties = []
        if not is_deposit and words:
            counterparties.append("0x" + words[0][-40:])
            # relayer is indexed in the canonical Withdrawal event ABI.
            if len(event["topics"]) > 1 and int(event["topics"][1], 16):
                counterparties.append("0x" + event["topics"][1][-40:])
        exact_time = utc(int(words[1], 16)) if is_deposit and len(words) >= 2 else None
        txs.append({"hash": event["transactionHash"], "block": height, "time_utc": exact_time, "time_lower_utc": lower_time, "time_upper_utc": upper_time,
                    "time_precision": "exact event timestamp" if exact_time else "bounded by adjacent daily sampled blocks; time_utc unknown",
                    "direction": "in" if is_deposit else "out", "asset": pool["asset"], "symbol": pool["symbol"], "decimals": pool["decimals"],
                    "amount": units(denomination, pool["decimals"]), "amount_raw": str(denomination), "counterparties": counterparties,
                    "fee": "0", "fee_raw": "0", "fee_asset": "ETH", "raw_ref": event["raw_ref"], "kind": "pool_deposit" if is_deposit else "pool_withdrawal", "logIndex": event["logIndex"]})
        if not is_deposit and len(words) >= 3:
            relayer_fee = int(words[2], 16)
            recipient = "0x" + words[0][-40:]
            relayer = "0x" + event["topics"][1][-40:] if len(event["topics"]) > 1 else None
            txs[-1]["relayer_fee"] = units(relayer_fee, pool["decimals"])
            txs[-1]["relayer_fee_raw"] = str(relayer_fee)
            txs[-1]["counterparty_amounts"] = [{"address": recipient, "asset": pool["asset"], "amount": units(denomination - relayer_fee, pool["decimals"]), "amount_raw": str(denomination - relayer_fee)}]
            if relayer and relayer_fee:
                txs[-1]["counterparty_amounts"].append({"address": relayer, "asset": pool["asset"], "amount": units(relayer_fee, pool["decimals"]), "amount_raw": str(relayer_fee)})
        if not exact_time and (event["transactionHash"], number(event["logIndex"])) in prior_times:
            txs[-1].update(prior_times[event["transactionHash"], number(event["logIndex"])])
    document["txs"] = txs
    document["balance_now"], document["balance_errors"] = fetcher.balances("eth", address, [], snapshot, balance_head)
    if pool["asset"] != "ETH":
        extra, error = fetcher.balances("eth", address, [{"kind": "erc20", "asset": pool["asset"], "symbol": pool["symbol"], "decimals": pool["decimals"]}], snapshot, balance_head)
        document["balance_now"] = extra
        document["balance_errors"] = error
    document["balance_observation"] = fetcher.heads["eth"]
    document["activity_found"] = True
    document["coverage"]["complete"] = False  # Whole-address history intentionally omitted.
    document["coverage"]["pool_events_complete"] = not missing
    document["coverage"]["daily_balances_complete"] = not document["daily_balance_errors"]
    document["coverage"]["missing_ranges"] = missing
    deposits = sum(tx["kind"] == "pool_deposit" for tx in txs)
    withdrawals = len(txs) - deposits
    actual = next((number(b["amount_raw"]) for b in document["balance_now"] if b["asset"] == pool["asset"]), None)
    expected = (deposits - withdrawals) * denomination
    document["pool_validation"] = {"deposit_events": deposits, "withdrawal_events": withdrawals, "interface_next_index": pool["next_index"],
                                    "deposit_count_matches_next_index": deposits == pool["next_index"], "asset": pool["asset"], "expected_pool_principal_raw": str(expected),
                                    "balance_now_raw": str(actual) if actual is not None else None, "difference_raw": str(actual - expected) if actual is not None else None,
                                    "match": actual == expected and not missing and head == balance_head, "conclusive": head == balance_head and not missing,
                                    "explanation": "Pool principal = (Deposit count - Withdrawal count) * denomination. Unsolicited donations, ERC20 refund handling, missing logs, or nonstandard token accounting can produce differences; inspect direct snapshots independently.",
                                    "raw_refs": pool["raw_refs"]}
    save_json(path, document)
    return document
