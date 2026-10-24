"""Publish this process’s evidence-linked coverage and validation summaries."""
import csv
from collections import Counter
from client import ROOT, RAW, read_json
from fetch import load_addresses


def main():
    report = read_json(RAW / "reports/validation.json.gz")
    bootstrap = load_addresses(ROOT / "data/bootstrap/fetch_evm.csv")
    ledger = load_addresses(ROOT / "data/addresses.csv") if (ROOT / "data/addresses.csv").exists() else {}
    lines = ["## Acquisition and validation result", "", f"Generated from saved evidence at `{report['generated_at']}` by `scripts/fetch/evm/validate.py`.", "",
             f"Input: **{len(bootstrap)} distinct valid bootstrap EVM addresses**; **{len(ledger)} distinct valid ledger EVM addresses**. Malformed EVM input rows are retained as unqueryable coverage entries: **{len(report['unqueryable_input_rows'])}**.", "",
             "| Chain | Timeline files (address/chain pairs) | Complete ordinary histories | Activity observed within checked data | Records | Native balance observations | Daily pool samples |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for chain in ("eth", "bsc", "arb", "polygon", "base", "op", "avax", "etc"):
        counts = report["chains"].get(chain, {})
        lines.append(f"| {chain} | {counts.get('timeline_files', 0)} | {counts.get('complete_histories', 0)} | {counts.get('active_addresses', 0)} | {counts.get('records', 0)} | {counts.get('native_balances', 0)} | {counts.get('daily_snapshots', 0)} |")
    lines += ["", f"Total **{report['timeline_files']} address/chain timeline files** containing **{report['transaction_transfer_event_records']} transaction, internal-transfer, ERC20-transfer, or pool-event records**. These record types are not unique transactions, persons, or designation actions. The same address can appear on several chains.", "",
              f"Records with exact timestamps: **{sum(c.get('records_with_exact_time', 0) for c in report['chains'].values())}**. Identified pools with complete event logs: **{sum(p['log_coverage']['complete'] for p in report['pools'])} of {len(report['pools'])} contracts**.", "",
              f"Unproduced expected address/chain pairs: **{len(report['missing_bootstrap_pairs'])}**. Schema/evidence errors: **{len(report['schema_or_evidence_errors'])}**. Referenced raw files: **{report['referenced_raw_files']}**.", "",
              "Source: `data/raw/evm/reports/coverage.json.gz` (one row per timeline, with raw_ref) and `validation.json.gz`. Every coverage row links the timeline, whose records link saved requests and responses.", "",
              f"Balance validation covers **{report['sample_addresses']} ordinary ETH addresses** in the mandatory sample, including the three largest acquired ordinary histories (**{', '.join(str(n) for n in report['big_sample_records'])} records**), plus all other available address/asset observations and every identified pool contract. **{report['sample_native_matches']} of {report['sample_addresses']} native ETH checks match conclusively.** Asset-check results: `{report['validation_asset_checks']}`. These are address/asset checks, not distinct-address counts.", "",
              "| Mandatory sample address | Records | Exact asset matches | Conclusive asset mismatches | Inconclusive asset checks |",
              "|---|---:|---:|---:|---:|"]
    for sample in report["sample"]:
        checks = sample["checks"]
        matched = sum(c["match"] and c["conclusive"] for c in checks)
        mismatched = sum(not c["match"] and c["conclusive"] for c in checks)
        inconclusive = sum(not c["conclusive"] for c in checks)
        lines.append(f"| `{sample['address']}` | {sample['records']} | {matched} | {mismatched} | {inconclusive} |")
    lines += ["", "Every mismatch includes its integer difference, balance block, raw reference, and evidenced cause or unresolved limitation in `validation.json.gz`. A different-block comparison or incomplete source history is not counted as a conclusive reconciliation.", "",
              "| Pool contract | Deposit events | Withdrawal events | Deposit count matches nextIndex | Daily samples | Full event logs | Principal balance matches |",
              "|---|---:|---:|---|---:|---|---|"]
    for pool in report["pools"]:
        lines.append(f"| `{pool['address']}` | {pool['deposit_events']} | {pool['withdrawal_events']} | {pool['deposit_count_matches_next_index']} | {pool['daily_snapshots']} | {pool['log_coverage']['complete']} | {pool['match']} |")
    lines += ["", "Pool principal mismatches are reported as the observed asset balance minus the Deposit/Withdrawal principal model, with exact base units in each contract's `pool_validation`. Extra balances outside that event model are not silently attributed to a sender or assigned a causal transaction. Direct daily measurements remain independent evidence."]
    summary = "\n".join(lines) + "\n"
    path = ROOT / "docs/sources/EVM.md"
    marker = "<!-- fetch_evm-results -->"
    prefix = path.read_text().split(marker)[0].rstrip()
    path.write_text(prefix + "\n\n" + marker + "\n\n" + summary)
    coverage_path = ROOT / "docs/COVERAGE.md"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    existing = coverage_path.read_text() if coverage_path.exists() else ""
    marker = "<!-- fetch_evm-coverage -->"
    if marker not in existing:
        brief = ["", marker, "", "## fetch_evm — EVM address histories", "", f"Evidence snapshot: `{report['generated_at']}`. Source details and final tables: `docs/sources/EVM.md`.", "",
                 f"Produced {report['timeline_files']} address/chain timelines and {report['transaction_transfer_event_records']} heterogeneous transfer/transaction/pool-event records. Expected pairs without files: {len(report['missing_bootstrap_pairs'])}; malformed input rows explicitly unqueryable: {len(report['unqueryable_input_rows'])}. Records and address/chain pairs are different units.", "",
                 "ETH/Arbitrum/Polygon use Etherscan v2 with adaptive block ranges; Optimism uses native Blockscout v2 after the legacy endpoint's persistent HTTP 429s. BSC and Base lack an accessible complete history index under the available free API plan; their state observations and full missing ranges are explicit. ETC uses the available Blockscout instance; see its row and raw errors for actual coverage. Avalanche C support is implemented, but no input row requested that chain.", "",
                 f"Identified pools with per-contract validation: {len(report['pools'])}. Pools use Deposit/Withdrawal RPC logs and independent daily archive balances, with separate event/daily completeness flags. Whole-address completeness is false because unrelated tokens, administrative calls, native donations and ERC20-pool refunds are outside this event scope. Full contract checks and extra-principal differences are retained, not suppressed.", "",
                 f"Mandatory ordinary-ETH validation sample: {report['sample_addresses']} addresses, including three large histories. All available assets are also checked. Results in address/asset-check units: {report['validation_asset_checks']}. Unresolved mismatches and source limits remain visible in `data/raw/evm/reports/validation.json.gz`; `coverage.json.gz` has every pair and raw_ref.", "",
                 "A zero current balance or no history found is a statement about data checked. It does not prove no past native/token inflow. Same-address activity on another chain is marked `same address, other chain`; it is not another OFAC-listed address. No issuer freeze or legal conclusion is inferred here.", ""]
        with coverage_path.open("a") as f:
            f.write("\n".join(brief))
    print(path.relative_to(ROOT), coverage_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
