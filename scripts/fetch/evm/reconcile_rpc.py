"""Audit native-history holes using canonical transactions named by internals.

An internal transfer's outer transaction need not directly involve the address.
When it does, an absent normal transaction is supplemented from RPC, with its
receipt and the original timestamp evidence retained. No unrelated tx is added.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json

from client import Client, APIError, ROOT, RAW, read_json, save_json, now, acquire_chain_locks
from fetch import normalized, number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", action="append", required=True)
    args = parser.parse_args()
    locks = acquire_chain_locks(["eth"])
    client = Client()
    report = {"generated_at": now(), "addresses": [], "errors": []}
    for address in args.address:
        address = address.lower()
        path = ROOT / f"data/timelines/eth/{address}.json.gz"
        doc = read_json(path)
        known = {tx["hash"] for tx in doc["txs"] if tx["kind"] == "normal"}
        candidates = {}
        for tx in doc["txs"]:
            if tx["kind"] == "internal" and tx["hash"] not in known:
                candidates[tx["hash"]] = tx
        hashes = sorted(candidates)
        refs, additions, audited_elsewhere = [], [], 0

        def batch(group):
            calls = [call for h in group for call in [("eth_getTransactionByHash", [h]), ("eth_getTransactionReceipt", [h])]]
            values, ref = client.batch("https://rpc.mevblocker.io", calls)
            return group, values, ref

        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = [pool.submit(batch, hashes[i:i + 30]) for i in range(0, len(hashes), 30)]
            for future in as_completed(jobs):
                try:
                    group, values, ref = future.result()
                    refs.append(ref)
                    for i, h in enumerate(group):
                        (tx, tx_error), (receipt, receipt_error) = values[i * 2:i * 2 + 2]
                        if tx_error or receipt_error or not tx or not receipt:
                            raise APIError(f"RPC transaction/receipt unavailable for {h}", ref)
                        recipient = (tx.get("to") or receipt.get("contractAddress") or "").lower()
                        sender = tx["from"].lower()
                        if address not in {sender, recipient}:
                            audited_elsewhere += 1
                            continue
                        prior = candidates[h]
                        if number(tx["blockNumber"]) != prior["block"]:
                            raise APIError(f"Canonical block differs from indexed internal transfer: {h}", ref)
                        timestamp = int(datetime.fromisoformat(prior["time_utc"].replace("Z", "+00:00")).timestamp())
                        fee = number(receipt["gasUsed"]) * number(receipt.get("effectiveGasPrice", tx.get("gasPrice")))
                        fee += number(receipt.get("blobGasUsed")) * number(receipt.get("blobGasPrice"))
                        row = {"hash": h, "blockNumber": number(tx["blockNumber"]), "timeStamp": timestamp, "from": sender, "to": recipient,
                               "value": str(number(tx["value"])), "gasUsed": str(number(receipt["gasUsed"])), "gasPrice": str(number(receipt.get("effectiveGasPrice", tx.get("gasPrice")))),
                               "fee_total_raw": str(fee), "isError": "1" if number(receipt["status"]) == 0 else "0", "transactionIndex": number(tx["transactionIndex"])}
                        item = normalized(row, "txlist", address, "ETH", ref + "#/response")
                        item.update({"rpc_response_id": i * 2, "receipt_raw_ref": ref + "#/response", "receipt_rpc_response_id": i * 2 + 1,
                                     "time_raw_ref": prior["raw_ref"], "supplement": "Canonical outer transaction absent from explorer txlist but named by its internal history"})
                        additions.append(item)
                except APIError as exc:
                    report["errors"].append({"address": address, "reason": str(exc), "raw_ref": exc.raw_ref})
        doc["txs"].extend(additions)
        doc["txs"].sort(key=lambda tx: (tx["block"], number(tx.get("transactionIndex")), tx["kind"], str(tx.get("traceId", ""))))
        audit = {"address": address, "outer_hashes_audited": len(hashes), "normal_records_added": len(additions), "outer_transactions_not_directly_involving_address": audited_elsewhere,
                 "raw_refs": refs, "errors": [e for e in report["errors"] if e["address"] == address], "audited_at": now()}
        doc["rpc_normal_audit"] = audit
        doc["coverage"]["notes"].append("Normal history supplemented from canonical RPC transactions/receipts named by internal transfers; see rpc_normal_audit. Explorer list completeness alone did not prove arithmetic completeness.")
        if audit["errors"]:
            doc["coverage"]["complete"] = False
            doc["coverage"]["missing_ranges"].append({"reason": "Canonical normal-transaction audit could not finish", "errors": audit["errors"]})
        save_json(path, doc)
        report["addresses"].append(audit)
        print(json.dumps({k: v for k, v in audit.items() if k not in {"raw_refs", "errors"}}), flush=True)
        save_json(RAW / "reports/rpc_reconciliation.json.gz", report)
    for handle in locks:
        handle.close()
    return bool(report["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
