"""Enrich pool withdrawals using Etherscan getLogs timestamps, never txlist.

Only timestamps are joined: authoritative event records remain the saved RPC
logs. All events in a block share its timestamp, including capped boundary logs.
"""
import bisect
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import threading

from client import APIError, Client, RAW, ROOT, now, read_json, save_json, acquire_chain_locks
from fetch import number, utc

WITHDRAWAL = "0xe9e508bad6d4c3227e881ca19068f099da81b5164dd6d62b2eaf1e8bc6c34931"


def main():
    c = Client()
    locks = acquire_chain_locks(["eth"])
    index_path = RAW / "reports/event_block_times.json.gz"
    existing = read_json(index_path) if index_path.exists() else {"blocks": {}}
    blocks = existing["blocks"]
    lock = threading.Lock()
    report = {"started_at": now(), "pools": [], "errors": []}

    def enrich(path):
        doc = read_json(path)
        if not doc.get("tornado_pool"):
            return None
        wanted = {tx["block"] for tx in doc["txs"] if tx["kind"] == "pool_withdrawal" and not tx.get("time_utc")}
        with lock:
            missing = sorted(wanted - {int(h) for h in blocks})
        cursor = missing[0] if missing else None
        pages = 0
        while cursor is not None and cursor <= missing[-1]:
            rows, ref = c.etherscan(1, "getLogs", module="logs", address=doc["address"], fromBlock=cursor, toBlock=missing[-1], topic0=WITHDRAWAL, page=1, offset=1000)
            if not rows:
                break
            with lock:
                for i, row in enumerate(rows):
                    block = number(row["blockNumber"])
                    timestamp = number(row["timeStamp"])
                    blocks[str(block)] = {"time_utc": utc(timestamp), "block_hash": row.get("blockHash"), "raw_ref": f"{ref}#/response/result/{i}/timeStamp"}
                pages += 1
                if pages % 10 == 0:
                    save_json(index_path, {"blocks": blocks, "updated_at": now()})
            # One observed timestamp suffices for every event in the boundary
            # block; no token/deposit/withdrawal record is acquired here.
            cursor = max(number(row["blockNumber"]) for row in rows) + 1
        changed = 0
        unknown = []
        rpc_hashes = {number(event["blockNumber"]): event.get("blockHash") for event in doc.get("pool_logs", [])}
        for tx in doc["txs"]:
            if tx.get("time_utc"):
                continue
            observed = blocks.get(str(tx["block"]))
            if observed and observed.get("block_hash") and rpc_hashes.get(tx["block"]) and observed["block_hash"].lower() != rpc_hashes[tx["block"]].lower():
                observed = None
            if observed:
                tx["time_utc"] = observed["time_utc"]
                tx["time_raw_ref"] = observed["raw_ref"]
                tx["time_precision"] = "exact block timestamp from Etherscan log response"
                changed += 1
            else:
                unknown.append(tx["block"])
        doc["timestamp_coverage"] = {"complete": not unknown, "unknown_records": len(unknown), "unknown_blocks": sorted(set(unknown)), "enriched_at": now(), "method": "getLogs timestamps joined by exact block number"}
        with lock:
            save_json(index_path, {"blocks": blocks, "updated_at": now()})
        save_json(path, doc)
        return {"address": doc["address"], "enriched_records": changed, "unknown_records": len(unknown), "raw_ref": str(path.relative_to(ROOT))}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(enrich, p): p for p in sorted((ROOT / "data/timelines/eth").glob("*.json.gz"))}
        for future in as_completed(futures):
            try:
                row = future.result()
                if row:
                    report["pools"].append(row)
                    print(json.dumps(row), flush=True)
            except (APIError, ValueError, KeyError) as exc:
                row = {"file": str(futures[future].relative_to(ROOT)), "reason": str(exc), "raw_ref": getattr(exc, "raw_ref", None)}
                report["errors"].append(row)
                print(json.dumps(row), flush=True)
            save_json(RAW / "reports/timestamp_enrichment.json.gz", report)
    for handle in locks:
        handle.close()
    return bool(report["errors"] or any(p["unknown_records"] for p in report["pools"]))


if __name__ == "__main__":
    raise SystemExit(main())
