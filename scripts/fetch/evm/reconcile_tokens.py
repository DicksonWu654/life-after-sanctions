"""Evidence-backed explanations for WETH supply events and token mismatches.

Writes validation evidence only. Never invents an adjustment for an unknown
token or equates a misleading Transfer log with an actual balance change.
"""
from client import Client, APIError, ROOT, RAW, now, read_json, save_json
from fetch import Fetcher, number
from tornado import full_logs, signature, ARCHIVE

WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def main():
    report = read_json(RAW / "reports/validation.json.gz")
    client = Client()
    fetcher = Fetcher(client)
    deposit, dep_ref = signature(fetcher, "Deposit(address,uint256)")
    withdrawal, wd_ref = signature(fetcher, "Withdrawal(address,uint256)")
    transfer, transfer_ref = signature(fetcher, "Transfer(address,address,uint256)")
    result = {"generated_at": now(), "records": [], "errors": []}
    target = RAW / "reports/reconciliation_causes.json.gz"
    for address_check in report["all_address_checks"]:
        if address_check["chain"] != "eth" or address_check["pool"]:
            continue
        check = next((c for c in address_check["checks"] if c["asset"] == WETH and not c["match"] and c["conclusive"]), None)
        if not check:
            continue
        address = address_check["address"]
        doc = read_json(ROOT / address_check["raw_ref"])
        try:
            logs, ranges, gaps = full_logs(fetcher, WETH, 0, doc["coverage"]["to_block"], [deposit, withdrawal], extra_topics=["0x" + address[2:].zfill(64)])
            correction = sum(number(row["data"]) * (1 if row["topics"][0].lower() == deposit.lower() else -1) for row in logs)
            expected = number(check["in_minus_out_minus_fees_raw"]) + correction
            actual = number(check["balance_now_raw"])
            record = {"chain": "eth", "address": address, "asset": WETH, "kind": "weth_supply_events", "correction_raw": str(correction),
                      "to_block": doc["coverage"]["to_block"],
                      "adjusted_expected_raw": str(expected), "balance_now_raw": str(actual), "adjusted_match": expected == actual and not gaps,
                      "explanation": "WETH Deposit mints and Withdrawal burns are supply changes outside the ERC20 Transfer-event list. Their signed total is an independent accounting adjustment.",
                      "events": len(logs), "complete": not gaps, "missing_ranges": gaps, "raw_refs": [r["raw_ref"] for r in ranges] + [dep_ref, wd_ref], "source_url": ARCHIVE}
            result["records"].append(record)
            print(address, "WETH supply adjustment matches:", record["adjusted_match"], flush=True)
        except (APIError, ValueError) as exc:
            result["errors"].append({"address": address, "asset": WETH, "reason": str(exc), "raw_ref": getattr(exc, "raw_ref", None)})
        save_json(target, result)
    # Bounded block-level checks for distinct nonstandard assets in the mandatory
    # sample. An observed mismatch invalidates the Transfer-only balance model.
    selected = set()
    for sample in report["sample"]:
        if len(selected) >= 8:
            break
        doc = read_json(ROOT / sample["raw_ref"])
        for check in sample["checks"]:
            asset = check["asset"]
            if asset in selected or not asset.startswith("0x") or asset == WETH or check["match"] or not check["conclusive"]:
                continue
            selected.add(asset)
            tx = next((t for t in doc["txs"] if t["asset"] == asset and number(t["amount_raw"]) and t["direction"] != "self"), None)
            if not tx:
                continue
            address, block = doc["address"], tx["block"]
            try:
                calls = [("eth_call", [{"to": asset, "data": "0x70a08231" + address[2:].zfill(64)}, hex(h)]) for h in (block - 1, block)]
                values, state_ref = client.batch(ARCHIVE, calls)
                if any(error or not isinstance(value, str) or len(value) != 66 for value, error in values):
                    raise APIError("Historical balanceOf did not return an ABI uint256 word", state_ref)
                change = number(values[1][0]) - number(values[0][0])
                logs, logs_ref = client.rpc(ARCHIVE, "eth_getLogs", [{"address": asset, "fromBlock": hex(block), "toBlock": hex(block), "topics": [transfer]}])
                net = 0
                for event in logs:
                    if len(event["topics"]) != 3 or len(event["data"]) != 66:
                        continue
                    sender, recipient = "0x" + event["topics"][1][-40:], "0x" + event["topics"][2][-40:]
                    value = number(event["data"])
                    net += value * (int(recipient.lower() == address) - int(sender.lower() == address))
                record = {"chain": "eth", "address": address, "asset": asset, "kind": "event_state_block_audit", "block": block,
                          "transfer_net_raw": str(net), "balance_change_raw": str(change), "nonstandard_accounting_observed": net != change,
                          "explanation": "At the sampled block, all matching RPC Transfer logs are compared to archive balanceOf before/after. A difference proves Transfer-only accounting does not equal state changes at that block; the entire present-day discrepancy is not automatically adjusted.",
                          "raw_refs": [state_ref, logs_ref, transfer_ref], "source_url": ARCHIVE}
                result["records"].append(record)
                print(address, asset, "event/state mismatch:", net != change, flush=True)
            except (APIError, ValueError) as exc:
                result["errors"].append({"address": address, "asset": asset, "reason": str(exc), "raw_ref": getattr(exc, "raw_ref", None)})
            save_json(target, result)
            if len(selected) >= 8:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
