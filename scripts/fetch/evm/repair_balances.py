"""Re-observe balances at each timeline's exact history end for reconciliation.

This is useful when a public node pruned a pinned block during a long fetch.
Every observation keeps its exact block and raw response; no zero substitution.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from client import APIError, Client, ROOT, RAW, now, read_json, save_json, acquire_chain_locks
from chains import CHAINS
from fetch import Fetcher, number, utc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chains", default=",".join(CHAINS))
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--latest", action="store_true", help="Re-observe a fresh pinned head for each group of 20 addresses")
    parser.add_argument("--only-errors", action="store_true")
    parser.add_argument("--report-name", default="balance_repair")
    parser.add_argument("--address", action="append")
    args = parser.parse_args()
    if not args.report_name.replace("_", "").replace("-", "").isalnum():
        parser.error("Invalid report name")
    fetcher = Fetcher(Client())
    locks = acquire_chain_locks(args.chains.split(","))
    report = {"started_at": now(), "repaired": [], "errors": []}

    def repair(path, override=None):
        doc = read_json(path)
        chain, address = doc["chain"], doc["address"]
        height = override["block"] if override else doc["coverage"]["to_block"]
        rpc = CHAINS[chain]["rpc"]
        values, ref = fetcher.c.batch(rpc, [("eth_getBalance", [address, hex(height)]), ("eth_getTransactionCount", [address, hex(height)]), ("eth_getCode", [address, hex(height)])])
        snapshot = {"balance": values[0][0], "nonce": values[1][0], "code": values[2][0], "errors": [e for _, e in values if e], "raw_ref": ref, "batch_index": 0}
        balances, errors = fetcher.balances(chain, address, doc["txs"], snapshot, height)
        if not any(b["asset"] == CHAINS[chain]["symbol"] for b in balances):
            raise APIError("No native balance returned at history end", ref)
        if doc.get("tornado_pool") and doc["pool_interface"]["asset"] != "ETH":
            asset = doc["pool_interface"]
            balances, errors = fetcher.balances(chain, address, [*doc["txs"], {"kind": "erc20", "asset": asset["asset"], "symbol": asset["symbol"], "decimals": asset["decimals"]}], snapshot, height)
        doc["prior_balance_observation"] = doc.get("balance_observation")
        doc["balance_now"], doc["balance_errors"] = balances, errors
        doc["source"]["balance"] = balances[0]["source"] if balances else rpc
        doc["balance_observation"] = {"block": height, "time_utc": override["time_utc"] if override else doc["coverage"].get("to_time"), "observed_at": now(), "raw_ref": ref,
                                      "note": "Observed at a fresh pinned head." if override else "Observed at pinned history end for exact reconciliation; time/block explicitly stated."}
        if override:
            doc["balance_observation"]["block_raw_ref"] = override["raw_ref"]
        doc["coverage"]["balances_complete"] = not errors
        doc["nonce_now"] = number(snapshot["nonce"]) if snapshot["nonce"] is not None else doc.get("nonce_now")
        if snapshot.get("code") is not None:
            doc["contract"] = snapshot["code"] != "0x"
            doc["contract_raw_ref"] = ref
            doc["contract_rpc_response_id"] = 2
        doc["activity_found"] = bool(doc["txs"] or doc.get("nonce_now") or any(number(b["amount_raw"]) for b in balances) or doc.get("contract"))
        if doc.get("pool_validation"):
            pool = doc["pool_validation"]
            actual = next((number(b["amount_raw"]) for b in balances if b["asset"] == pool["asset"]), None)
            expected = number(pool["expected_pool_principal_raw"])
            pool.update({"balance_now_raw": str(actual) if actual is not None else None, "difference_raw": str(actual - expected) if actual is not None else None,
                         "conclusive": doc["log_coverage"]["complete"] and height == doc["coverage"]["to_block"],
                         "match": actual == expected and doc["log_coverage"]["complete"] and height == doc["coverage"]["to_block"]})
        save_json(path, doc)
        return {"chain": chain, "address": address, "balance_assets": len(balances), "balance_errors": len(errors), "raw_ref": str(path.relative_to(ROOT))}

    for chain in args.chains.split(","):
        paths = sorted((ROOT / "data/timelines" / chain).glob("*.json.gz"))
        if args.address:
            requested = {a.lower() for a in args.address}
            paths = [p for p in paths if p.name.split(".")[0] in requested]
        if args.only_errors:
            paths = [p for p in paths if (lambda d: d.get("balance_errors") or not any(b["asset"] == CHAINS[chain]["symbol"] for b in d["balance_now"]))(read_json(p))]
        group_size = 20 if args.latest else max(1, len(paths))
        for start in range(0, len(paths), group_size):
            group = paths[start:start + group_size]
            override = None
            if args.latest:
                value, head_ref = fetcher.rpc(chain, "eth_blockNumber", [], fresh=True)
                height = max(0, number(value) - 4)
                block, ref = fetcher.block(chain, height)
                override = {"block": height, "time_utc": utc(block["timestamp"]), "raw_ref": ref, "head_raw_ref": head_ref}
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(repair, p, override): p for p in group}
                for future in as_completed(futures):
                    try:
                        row = future.result()
                        report["repaired"].append(row)
                    except APIError as exc:
                        row = {"file": str(futures[future].relative_to(ROOT)), "reason": str(exc), "raw_ref": exc.raw_ref}
                        report["errors"].append(row)
                    print(json.dumps(row), flush=True)
                    save_json(RAW / f"reports/{args.report_name}.json.gz", report)
    for handle in locks:
        handle.close()
    return bool(report["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
