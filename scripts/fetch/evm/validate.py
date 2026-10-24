"""Offline structure, evidence, address coverage and integer balance checks."""
from collections import Counter, defaultdict
import csv
import gzip
import json
import bisect
from pathlib import Path

from chains import CHAINS
from client import RAW, ROOT, now, read_json, save_json
from fetch import load_addresses, number, units


def balance_checks(doc, causes=None):
    """Use integer base units; self transfers affect only the sender's fees."""
    totals, fees = defaultdict(int), 0
    for tx in doc["txs"]:
        value = number(tx["amount_raw"])
        if tx["direction"] == "in":
            totals[tx["asset"]] += value
        elif tx["direction"] == "out":
            totals[tx["asset"]] -= value
        fees += number(tx.get("fee_raw"))
    native = CHAINS[doc["chain"]]["symbol"]
    totals[native] -= fees
    checks = []
    for balance in doc["balance_now"]:
        asset = balance["asset"]
        observed = number(balance["amount_raw"])
        expected = totals[asset]
        delta = expected - observed
        if doc.get("tornado_pool"):
            reason = "Pool principal events exclude donations/refunds and unrelated token transfers; see pool_validation and direct daily balances."
        elif not doc["coverage"].get("complete"):
            reason = "Incomplete history; missing ranges are enumerated in this timeline."
        elif balance["block"] != doc["coverage"]["to_block"]:
            reason = "Balance and history end at different blocks; refresh history before claiming a reconciliation."
        elif delta == 0:
            reason = "Exact integer reconciliation."
        elif asset == native and doc["chain"] in {"op", "base", "arb"}:
            reason = "Unresolved: inspect L1 data fees, fee accounting and explorer internal-transfer coverage; no cause proven."
        elif asset != native:
            reason = "Unresolved: transfer-event totals differ from balanceOf; nonstandard/rebasing/tax/spam-token behavior or index gaps require investigation."
        else:
            reason = "Unresolved native discrepancy; inspect internal/creation transfers, fees and explorer indexing."
        conclusive = doc["coverage"].get("complete") and balance["block"] == doc["coverage"]["to_block"]
        checks.append({"asset": asset, "decimals": balance["decimals"], "symbol": balance["symbol"], "in_minus_out_minus_fees_raw": str(expected),
                       "balance_now_raw": str(observed), "difference_raw": str(delta), "difference": units(delta, balance["decimals"]),
                       "match": abs(delta) <= (1 if asset == native else 0), "conclusive": conclusive, "cause_or_limitation": reason,
                       "balance_raw_ref": balance["raw_ref"], "balance_block": balance["block"]})
        for cause, cause_ref in (causes.get((doc["chain"], doc["address"], asset), []) if causes else []):
            if cause["kind"] == "weth_supply_events" and cause.get("to_block") == doc["coverage"]["to_block"] and cause["balance_now_raw"] == balance["amount_raw"]:
                checks[-1].update({"cause_or_limitation": cause["explanation"], "accounting_adjustment_raw": cause["correction_raw"], "adjusted_expected_raw": cause["adjusted_expected_raw"],
                                   "explained": cause["adjusted_match"], "cause_raw_ref": cause_ref})
            elif cause["kind"] == "event_state_block_audit" and cause.get("nonstandard_accounting_observed"):
                checks[-1].update({"cause_or_limitation": f"RPC block {cause['block']} shows Transfer-event net {cause['transfer_net_raw']} base units, but balanceOf changed {cause['balance_change_raw']} base units. Transfer-only accounting is invalid at that block; the entire current difference remains unadjusted.",
                                   "nonstandard_event_accounting_proven": True, "cause_raw_ref": cause_ref})
    return checks


def refs_in(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("raw_ref") and isinstance(item, str):
                yield item
            elif key.endswith("raw_refs") and isinstance(item, list):
                yield from (v for v in item if isinstance(v, str))
            elif isinstance(item, (dict, list)):
                yield from refs_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from refs_in(item)


def pool_daily_checks(doc):
    asset = doc["pool_validation"]["asset"]
    heights, prefix = [], [0]
    for tx in sorted(doc["txs"], key=lambda x: x["block"]):
        heights.append(tx["block"])
        sign = 1 if tx["kind"] == "pool_deposit" else -1
        prefix.append(prefix[-1] + sign * number(tx["amount_raw"]))
    counts, examples = Counter(), []
    for row in doc.get("daily_balance", []):
        if row["block"] > doc["log_coverage"]["to_block"]:
            counts["beyond_event_history"] += 1
            continue
        balance = next((b for b in row["assets"] if b["asset"] == asset), None)
        if balance is None:
            counts["underlying_asset_not_observed"] += 1
            continue
        expected = prefix[bisect.bisect_right(heights, row["block"])]
        difference = number(balance["amount_raw"]) - expected
        counts["match" if difference == 0 else "above_principal" if difference > 0 else "below_principal"] += 1
        if difference and len(examples) < 5:
            examples.append({"date": row["date"], "block": row["block"], "expected_principal_raw": str(expected), "observed_raw": balance["amount_raw"],
                             "difference_raw": str(difference), "raw_ref": row["raw_ref"], "rpc_response_id": balance["rpc_response_id"]})
    return {"asset": asset, "counts": dict(counts), "conclusive_event_scope": doc["log_coverage"]["complete"], "first_differences": examples,
            "limitation": "Independent archive balances versus pool-principal events at the same block. Differences are outside the principal-event model; absent pre-deployment token observations are not filled with zero."}


def validate():
    errors, coverage, validations, pools = [], [], [], []
    refs = set()
    counts = defaultdict(Counter)
    causes = defaultdict(list)
    causes_path = RAW / "reports/reconciliation_causes.json.gz"
    if causes_path.exists():
        causes_document = read_json(causes_path)
        refs.update(part.strip().split("#")[0] for ref in refs_in(causes_document) for part in ref.split(";") if part.strip())
        for i, cause in enumerate(causes_document["records"]):
            causes[cause["chain"], cause["address"], cause["asset"]].append((cause, str(causes_path.relative_to(ROOT)) + f"#/records/{i}"))
    for chain in CHAINS:
        for path in sorted((ROOT / "data/timelines" / chain).glob("*.json.gz")):
            try:
                doc = read_json(path)
                assert doc["chain"] == chain and doc["address"] == path.name.split(".")[0]
                assert isinstance(doc["coverage"]["complete"], bool)
                assert all(tx["direction"] in {"in", "out", "self"} for tx in doc["txs"])
                assert all(units(tx["amount_raw"], tx["decimals"]) == tx["amount"] for tx in doc["txs"])
                assert all(tx["block"] <= doc["coverage"]["to_block"] for tx in doc["txs"])
                refs.update(part.strip().split("#")[0] for r in refs_in(doc) for part in r.split(";") if part.strip())
                counts[chain]["timeline_files"] += 1
                counts[chain]["complete_histories"] += int(doc["coverage"]["complete"])
                counts[chain]["active_addresses"] += int(doc.get("activity_found", bool(doc["txs"])))
                counts[chain]["records"] += len(doc["txs"])
                counts[chain]["records_with_exact_time"] += sum(bool(tx.get("time_utc")) for tx in doc["txs"])
                counts[chain]["native_balances"] += int(any(b["asset"] == CHAINS[chain]["symbol"] for b in doc["balance_now"]))
                counts[chain]["same_address_other_chain"] += int(doc.get("listing_relation") == "same address, other chain")
                counts[chain]["daily_snapshots"] += len(doc.get("daily_balance", []))
                counts[chain]["pools"] += int(doc.get("tornado_pool", False))
                timeline_ref = str(path.relative_to(ROOT))
                coverage.append({"chain": chain, "address": doc["address"], "listing_relation": doc.get("listing_relation"),
                                 "active": doc.get("activity_found"), "complete": doc["coverage"]["complete"], "from_block": doc["coverage"]["from_block"],
                                 "to_block": doc["coverage"]["to_block"], "records": len(doc["txs"]), "contract": doc.get("contract"), "pool": doc.get("tornado_pool", False),
                                 "daily_snapshots": len(doc.get("daily_balance", [])), "balance_errors": len(doc.get("balance_errors", [])),
                                 "missing_ranges": doc["coverage"].get("missing_ranges", []), "notes": doc["coverage"].get("notes", []), "raw_ref": timeline_ref})
                checks = balance_checks(doc, causes)
                validations.append({"chain": chain, "address": doc["address"], "records": len(doc["txs"]), "contract": doc.get("contract"), "pool": doc.get("tornado_pool", False),
                                    "coverage_complete": doc["coverage"]["complete"], "raw_ref": timeline_ref, "checks": checks})
                if doc.get("tornado_pool"):
                    daily = doc["daily_balance"]
                    assert len(daily) == len({row["date"] for row in daily})
                    assert all(row["time_utc"][:10] == row["date"] for row in daily)
                    assert all(daily[i]["block"] < daily[i + 1]["block"] for i in range(len(daily) - 1))
                    assert all(sum(number(part["amount_raw"]) for part in tx["counterparty_amounts"]) == number(tx["amount_raw"])
                               for tx in doc["txs"] if "counterparty_amounts" in tx)
                    pools.append({"address": doc["address"], "raw_ref": timeline_ref, "daily_snapshots": len(doc["daily_balance"]),
                                  "daily_errors": doc.get("daily_balance_errors", []), "log_coverage": doc.get("log_coverage"), "timestamp_coverage": doc.get("timestamp_coverage"),
                                  "daily_reconciliation": pool_daily_checks(doc), **doc["pool_validation"]})
            except (ValueError, OSError, AssertionError, KeyError, TypeError) as exc:
                errors.append({"file": str(path.relative_to(ROOT)), "error": f"{type(exc).__name__}: {exc}"})
    for ref in sorted(refs):
        path = ROOT / ref
        if not path.is_relative_to(ROOT) or not path.exists():
            errors.append({"missing_or_invalid_raw_ref": ref})
    bootstrap_path = ROOT / "data/bootstrap/fetch_evm.csv"
    missing = []
    invalid_inputs = []
    seen_missing = set()
    for input_path in [bootstrap_path, ROOT / "data/addresses.csv"]:
        if not input_path.exists():
            continue
        with input_path.open() as f:
            for row in csv.DictReader(f):
                from bootstrap import ADDRESS
                address = (row.get("address_normalized") or row.get("address") or "").lower()
                if address.startswith("0x") and not ADDRESS.fullmatch(address):
                    invalid_inputs.append({"chain": row.get("chain"), "address": address, "reason": "Invalid 20-byte EVM address shape; not queried or silently corrected", "raw_ref": row.get("raw_ref"), "input_file": str(input_path.relative_to(ROOT))})
        for address, info in load_addresses(input_path).items():
            for chain in info["chains"]:
                path = ROOT / f"data/timelines/{chain}/{address}.json.gz"
                if not path.exists() and (chain, address) not in seen_missing:
                    seen_missing.add((chain, address))
                    missing.append({"chain": chain, "address": address, "reason": "No timeline produced; see fetch_run failures", "raw_ref": "data/raw/evm/reports/fetch_run.json.gz"})
    # Mandatory sample: top 3 large Ethereum histories, plus 12 other nonempty
    # Ethereum histories. All addresses/assets are also checked in full above.
    eligible = sorted((v for v in validations if v["chain"] == "eth" and not v["pool"] and v["records"] and v["checks"]), key=lambda x: x["records"], reverse=True)
    sample = eligible[:3] + eligible[3:15]
    sample_addresses = {v["address"] for v in sample}
    status = Counter()
    for validation in validations:
        for check in validation["checks"]:
            status["matched" if check["match"] and check["conclusive"] else "explained_mismatch" if check.get("explained") and check["conclusive"] else "mismatched" if check["conclusive"] else "inconclusive"] += 1
    report = {"generated_at": now(), "chains": dict(counts), "timeline_files": len(coverage), "transaction_transfer_event_records": sum(c["records"] for c in counts.values()),
              "referenced_raw_files": len(refs), "schema_or_evidence_errors": errors, "missing_bootstrap_pairs": missing,
              "unqueryable_input_rows": invalid_inputs,
              "validation_asset_checks": dict(status), "sample_addresses": len(sample_addresses), "big_sample_records": [v["records"] for v in sample[:3]],
              "sample_native_matches": sum(any(c["asset"] == "ETH" and c["match"] and c["conclusive"] for c in v["checks"]) for v in sample),
              "sample": sample, "all_address_checks": validations, "pools": pools}
    save_json(RAW / "reports/validation.json.gz", report)
    save_json(RAW / "reports/coverage.json.gz", {"generated_at": report["generated_at"], "rows": coverage, "missing": missing, "unqueryable_inputs": invalid_inputs})
    print(json.dumps({k: v for k, v in report.items() if k not in {"sample", "all_address_checks", "pools"}}, indent=2))
    return int(bool(errors or missing or len(sample_addresses) < 15 or report["sample_native_matches"] < 15))


if __name__ == "__main__":
    raise SystemExit(validate())
