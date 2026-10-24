"""Generate docs/LABELS.md from validated label counts and recorded spot checks."""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re

try:
    from .build import OUT
    from .policy import BASE_CLASSES as CLASSES
    from .sources import ROOT
except ImportError:
    from build import OUT
    from policy import BASE_CLASSES as CLASSES
    from sources import ROOT


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    return ["| " + " | ".join(map(cell, headers)) + " |",
            "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(map(cell, row)) + " |" for row in rows]


def render() -> str:
    summary = json.loads((OUT / "summary.json").read_text())
    manifest = json.loads((OUT / "sources.json").read_text())
    stats = json.loads((OUT / "build_stats.json").read_text())
    rows = list(csv.DictReader((OUT / "labels.csv").open()))
    checks = list(csv.DictReader((OUT / "spot_checks.csv").open()))
    supplemental = json.loads((OUT / "supplemental_checks.json").read_text())
    assert summary["label_rows"] == len(rows) and len(checks) == 30
    lines = ["# Destination labels", "",
        f"The frozen build contains **{summary['label_rows']:,} label rows** for **{summary['unique_chain_addresses']:,} distinct (chain, address) pairs** across **{summary['chain_count']} chains**. "
        "These are source claims and research leads. They do not prove who controls an address, that a service handled a particular transaction, or that anyone violated the law.", "",
        f"Collection run: `{summary['collected_at']}`. This is the ingestion time; individual request timestamps, pinned revisions, content digests and raw paths are in `data/labels/sources.json` and `data/raw/labels/requests/`. "
        "Cached sources retain their original retrieval time. No balances, transaction counts or USD values are asserted by this table.", "",
        "## Outputs and reproduction", "",
        "- `data/labels/labels.csv`: requested columns, plus `source_id`, `source_url`, `raw_ref`, `evidence_locator`, `license`, `valid_from`, `valid_to`.",
        "- `data/labels/labels.sqlite`: identical rows, indexed on `(chain, address_normalized)`; CSV digest in its metadata table.",
        "- `data/labels/sources.json`, `summary.json`, `build_stats.json`, `spot_checks.csv`, `supplemental_checks.json`: provenance, denominators, omissions and checks.",
        "- `data/labels/licenses/`: complete upstream repository license notices. API/page licensing is recorded separately below.",
        "- `data/raw/labels/`: gzip-compressed unmodified responses, frozen shared inputs, request metadata and archived collection manifests.", "",
        "All scripts use the Python standard library and the existing project venv; no dependency changes or credentials were needed.", "",
        "```sh", ".venv/bin/python -S scripts/labels/collect.py",
        ".venv/bin/python -S scripts/labels/build.py", ".venv/bin/python -S scripts/labels/validate.py",
        ".venv/bin/python -S scripts/labels/report.py", "",
        "# Offline acceptance checks; no network and no output writes:",
        ".venv/bin/python -S scripts/labels/build.py --check",
        ".venv/bin/python -S scripts/labels/validate.py --check",
        ".venv/bin/python -S scripts/labels/report.py --check", "```", "",
        "`collect.py` resumes by request URL and skips saved responses. `collect.py --refresh` refreshes mutable APIs/pages and snapshots the current shared CSVs; GitHub data stay pinned. "
        "New source bytes have distinct raw objects, and collection manifests are archived. Review changed source layouts/labels before accepting a refreshed build. "
        "HTTP 429 and transient server/network failures back off; individual downloads are bounded. No chain parquet is downloaded.", "",
        "```python", "from scripts.labels.lookup import label",
        "rows = label('ethereum', '0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc')", "```", "",
        "`label(chain, address)` returns every matching source claim as dictionaries, ordered by confidence; it returns `[]` for an unmatched address. "
        "A missing index raises an error. Chain names/tickers and supported numeric EVM IDs are accepted. EVM addresses are lowercased; BTC Base58 and Tron Base58 remain case-sensitive. "
        "Tron `41...`/`0x41...` hex is converted to Base58Check. `BNB` is kept separate from `BSC` (chain ID 56). "
        "The lookup does no network requests, graph propagation, address clustering or guessed labels. It returns all conflicts rather than choosing a winner.", "",
        "## Units and classification", "",
        "One row is one source label/class claim, with OFAC entity associations retained individually. A pair can have multiple sources, names and classes. "
        "Chain/class/source row totals must not be called distinct addresses or entities. Distinct pair counts within sources also overlap and must not be added across sources.", "",
        "`other_sanctioned` means membership in the supplied historical/current OFAC ledger. Names and UIDs come from `data/ledger.csv`, joined to `data/addresses.csv`; both inputs are frozen under the owned raw directory. "
        "The notes retain source XML/action references, current-list flags and listing/delisting dates. `valid_from`/`valid_to` are the ledger's designation interval where known. "
        "Blank dates mean unresolved/not supplied, not permanent validity. All service labels have unresolved historical validity unless their notes say otherwise. "
        "Tornado Cash's historical OFAC row is retained after delisting; its independently sourced protocol class remains separate.", "",
        "Role rules live in `scripts/labels/policy.py`. Official mixer configuration includes only mainnet pools, routers/proxies and RAILGUN privacy entry points. "
        "Tokens, governance, admins, bonders and other ancillary labels are not automatically mixer/bridge/DEX destinations. "
        "CEX deposit/hot classes require explicit role text and a specific exchange category; generic numbered exchange labels, deposit funders and untyped services stay `unknown_service`. "
        "The displayed `Bitget Dep: <address>` format is explicitly expanded to `Bitget Deposit: <address>` in the saved public explorer tooltip/title. "
        "Abbreviated deposit labels are accepted only when the exchange prefix agrees with the dataset category; category/name conflicts stay low-confidence `unknown_service`. "
        "Third-party phishing/scam labels are low-confidence allegations; an exploit/victim tag alone is omitted. `scam_poisoning` does not establish that address poisoning occurred. "
        "RAILGUN uses the research taxonomy `mixer`; this is not a sanctions claim. eXch name tags remain `unknown_service` because the retrieved name tags do not establish mixer/CEX taxonomy.", "",
        "High confidence means the address mapping is explicit in an official source/ledger, medium means an explicit public third-party label, and low means heuristic clusters, source replication uncertainty or unverified risk labels. "
        "These grades describe evidence for the mapping, not current ownership, legal status or transaction-time operation.", "",
        "## Counts by chain and class", "",
        "All class cells below are **label rows**; the address column counts distinct addresses within that chain. Zeros describe this build's coverage.", ""]
    headers = ["Chain", "Addresses", "Rows", *CLASSES]
    lines += table(headers, [[chain, record["unique_addresses"], record["label_rows"], *[record["classes"][role] for role in CLASSES]]
                             for chain, record in summary["by_chain"].items()])
    lines += ["", "Class totals (label rows):", ""]
    lines += table(["Class", "Rows"], summary["by_class"].items())
    lines += ["", "Confidence totals (label rows):", ""]
    lines += table(["Confidence", "Rows"], sorted(summary["by_confidence"].items()))
    lines += ["", "## Exact sources used and licenses", "",
        "Only the sources in this table feed `labels.csv`. Every source file and SHA-256 is enumerated in `data/labels/sources.json`; `source_ref` and `evidence_locator` identify each row's exact record. "
        "GitHub repository licenses are the upstream publishers' stated licenses, not an assertion that upstream explorer terms have been cleared. "
        "There is no blanket MIT license for the combined table. Sources with no established open-data license are identified as such; no permission to republish bulk original content is implied.", ""]
    lines += table(["ID / source", "Revision / snapshot", "Label rows", "Distinct chain/address pairs", "License / status", "Raw example"], [
        [f"`{source['source_id']}` [{source['name']}]({source['url']})", source["revision"],
         summary["by_source"][source["source_id"]]["label_rows"], summary["by_source"][source["source_id"]]["unique_chain_addresses"],
         source["license"], source["files"][0]["raw_ref"] if source["files"] else "No responses"]
        for source in manifest["sources"]])
    lines += ["", "Repository license texts are preserved in `data/labels/licenses/<source_id>.txt`; their original raw-response references are in `sources.json`. "
        "Across's source is BUSL-1.1 with a stated future GPL change, not an MIT dataset; only its factual deployed-address registry is extracted for this research. "
        "WalletExplorer's API page is not an open-data license. Its FAQ describes co-spend clustering and generally stale service names; all its labels are low confidence. "
        "TronScan account `name` and token names are not treated as third-party public tags.", "",
        "External intake status: **READ-ONLY REVIEW OK**. Selected repositories were resolved to their canonical owners and pinned commits through saved GitHub metadata before individual data files were fetched. "
        "No repository was cloned and no upstream package, build, configuration, JavaScript or TypeScript was executed. Files were parsed as JSON, CSV, HTML, Markdown or a narrow literal-address grammar. "
        "This records the bounded read-only step, not a security endorsement of upstream code. Preflight method: [SEAL developer-targeted intrusions](https://frameworks.securityalliance.org/devsecops/developer-targeted-intrusions/overview/).", "",
        "Other suggested datasets (OpenSanctions, Arkham, Chainabuse, CryptoScamDB, MistTrack/SlowMist and additional label repositories) do not feed this build. "
        "No license or coverage claim is made for those unused sources. Etherscan v2 nametag/free-tier access was not used; the eXch and Bitget checks use public address-page name tags.", "",
        "## Coverage and open uncertainties", ""]
    ofac_pairs = summary["validation"]["ofac_chain_addresses_preserved"]
    tornado_counts = collections.Counter(row["chain"] for row in rows if row["source_id"] == "tornado")
    tron_source = next(source for source in manifest["sources"] if source["source_id"] == "tronscan")
    wallet_source = next(source for source in manifest["sources"] if source["source_id"] == "walletexplorer")
    multi_claims = sum(row["source_id"] == "daws" and "Same address/name occurs on multiple source chain IDs" in row["notes"] for row in rows)
    malformed = sorted({(row["chain"], row["address_normalized"]) for row in rows
                        if row["source_id"] == "ofac" and "address_valid=false" in row["notes"]})
    lines += [
        f"- All **{ofac_pairs:,}** frozen OFAC chain/address pairs are retained, including historical and untrackable entries. "
        "Ledger-derived labels alone do not supply destination-service coverage for a chain.",
        "- Tornado Cash: all mainnet pool/router entries in the selected classic UI revision are included. Source-row counts by chain: "
        + ", ".join(f"{chain} {count}" for chain, count in sorted(tornado_counts.items())) + ". This does not claim coverage of every fork, later deployment, Nova contract or relayer.",
        "- Ethereum has the broadest mixer/DEX/bridge/DeFi/CEX coverage. ARB, OP, BSC, POLYGON and AVAX have selected explorer labels and official protocol supplements; "
        "BASE, GNO, CELO, FTM, WORLD, ARB_NOVA, LINEA and POLYGON_ZKEVM have narrower or less independently corroborated coverage. Never copy an EVM address label onto another chain.",
        f"- **{multi_claims:,} dawsbot label rows** repeat an address/name on multiple source chain IDs. These stay low confidence, with the source chain IDs in notes. "
        "The large AVAX/WORLD overlap is a source-quality concern, not proof of operation on both chains. Independent official labels remain separate high-confidence rows.",
        "- BTC covers OFAC-named Blender/Sinbad and selected WalletExplorer exchange/mixer clusters. "
        f"The script requests only the first 100 addresses from each of {len(wallet_source['files'])} named cluster responses; absent clusters and unreturned addresses are not extrapolated. "
        "WalletExplorer exchange clusters stay `unknown_service` because a cluster name does not distinguish customer deposits from hot/cold wallets. Modern BTC CEX and mixer coverage remains thin.",
        f"- TRX: inspected **{len(tron_source['files'])}** frozen shared TronScan account responses; "
        f"**{summary['by_source']['tronscan']['label_rows']}** supplied usable `addressTag`/`publicTag` rows. "
        "SUN.io official TRON mainnet tables add SunSwap v2/v3 and Universal Router contracts. Tron CEX deposit/hot, issuer operational wallets, mixers and BTTC gateway coverage remain thin; account self-names and token spam are not substituted for tags.",
        "- Bridges: official Wormhole, Hop, Across, legacy Stargate, Arbitrum One, OP mainnet, Base and Avalanche Bridge entries are included. "
        "Multichain is covered by third-party labels with historical/operational uncertainty. THORChain current vault/router endpoints come from the Liquify gateway linked by official developer documentation; "
        "vaults rotate, some chain entries are halted, and no historical vault inventory is implied. BTTC bridge gateways are not established by the retrieved sources; its token labels are not gateway labels.",
        "- LTC, DOGE, BCH, XRP and SOL have only sparse OFAC and/or current THORChain/Wormhole entries. BNB (Beacon), BSV, BTG, DASH, ETC, XMR, XVG and ZEC have essentially ledger-only service coverage. "
        "A label on XMR is still untrackable as a public transaction graph; the lookup does not change that.",
        "- ChipMixer and publicly documented Wasabi/Samourai coordinator addresses are not established here. No CoinJoin participant is labelled as a coordinator. "
        "eXch has public Ethereum name-tag leads; source copies on other chain IDs remain low confidence and no mixer role is invented.",
        "- `cex_deposit`/`cex_hot` coverage is selective; numbered exchange tags and deposit-funder patterns are insufficient. "
        "Issuer coverage is mostly EVM Circle/Tether-related tags. `scam_poisoning` coverage is selected EVM third-party risk tags only, not a complete dust/spam detection system.",
        "- Official contract inventories are snapshots and are not verified by code hash, deployment transaction, transaction-time operation or custody analysis. "
        "Shared infrastructure (multicall, wrapped native tokens and Permit2) is excluded from the official DEX/bridge supplements. Sending to a router does not by itself establish which action was executed.",
    ]
    if malformed:
        lines += ["- Ledger-invalid input addresses are preserved without padding or repair: " + ", ".join(f"`{chain}:{address}`" for chain, address in malformed) + "."]
    lines += ["", "This is the labels analysis’s chain-coverage note. It is kept in the owned `docs/LABELS.md`; the integrating worker can include it in the shared `docs/COVERAGE.md`.", "",
        "Omissions recorded by the build (input-record units unless named otherwise):", ""]
    lines += table(["Reason", "Records"], sorted(stats["omitted"].items()))
    lines += ["", "## Thirty random source spot checks", "",
        f"Uniform random sample without replacement over the sorted CSV's label rows; seed **{summary['validation']['spot_check_seed']}**. "
        "Each listed address/name was checked against its exact saved source record, source chain and role support. "
        "The CSV evidence file also records source URLs, raw paths, record locators and extracted source text. These checks verify transcription/classification support; they do not establish the source's ultimate accuracy or address control. "
        "The sample is dominated by the largest source; the separate source-balanced checks below supplement it.", ""]
    lines += table(["#", "Chain", "Address", "Source label", "Class", "Source", "Result"], [
        [row["number"], row["chain"], "`" + row["address_normalized"] + "`", row["label"], row["class"],
         f"{row['source_id']}; spot_checks.csv row {int(row['number']) + 1}", "PASS"] for row in checks])
    lines += ["", "Full evidence: `data/labels/spot_checks.csv` (the raw file and exact record are listed for every sampled label).", "",
        "Additional source-balanced checks (one per source with output rows):", ""]
    lines += table(["Source", "Chain", "Address", "Label / class", "Result"], [
        [row["source_id"], row["chain"], "`" + row["address_normalized"] + "`", row["label"] + " / " + row["class"], row["result"]]
        for row in supplemental])
    lines += ["", "## Acceptance verification", "",
        f"`build.py --check` reconstructs the CSV byte-for-byte from the frozen sources and compares every indexed row; CSV SHA-256: `{summary['csv_sha256']}`. "
        f"`validate.py --check` verifies **{summary['validation']['all_source_records_checked']:,} source-record references**, "
        f"**{summary['validation']['raw_files_checked']} raw source-file digests**, the OFAC pair set, the thirty recorded random checks, "
        f"and **{summary['validation']['supplemental_source_checks']}** supplemental source checks. "
        "Regression checks cover CEX funders/casinos, bridge bonders, mixer tokens, victim tags, chain separation, address case, Tron hex conversion, mainnet/testnet separation and unknown-address behavior. "
        "SQLite integrity and the `(chain, address_normalized)` query plan are checked. `report.py --check` reproduces this document. "
        "No downstream transaction-match rate or value-weighted label coverage was measured by this analysis.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Reproduce and compare docs/LABELS.md without writes")
    args = parser.parse_args()
    payload = render()
    target = ROOT / "docs/LABELS.md"
    # Round 2 is separately reproduced by round2_report.py; keep its appended
    # section when rebuilding or checking this frozen Round 1 report.
    if target.exists() and "\n## Round 2\n" in target.read_text():
        payload += "\n## Round 2\n" + target.read_text().split("\n## Round 2\n", 1)[1]
    if args.check:
        assert target.read_text() == payload, "LABELS.md has drifted from the evidence"
        print("LABELS.md check passed")
    else:
        target.write_text(payload)
        print("Wrote docs/LABELS.md")
