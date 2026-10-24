"""Fetch selected public label data as inert bytes. Never install/execute upstream code."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone

try:
    from .sources import ROOT, RAW, fetch, github_file
except ImportError:
    from sources import ROOT, RAW, fetch, github_file

PINS = {
    "brian": ("brianleect/etherscan-labels", "923aba72c7e2d0682f7ae6194b6140bd90668dc9", "MIT"),
    "daws": ("dawsbot/eth-labels", "d9b21aefeded56f7fce7208d6fa173d128526c1b", "MIT"),
    "tornado": ("tornadocash/tornado-classic-ui", "a83fae0772c8da084c0e76b3a756b456f5b9f5bb", "MIT"),
    "railgun": ("railgun-community/shared-models", "b37e643ef38e3df554deffa33f40530b20ce9065", "MIT"),
    "hop": ("hop-protocol/hop", "3ae90badbed5708d72cec46d0efeb004a4d0c587", "MIT"),
    "wormhole": ("wormhole-foundation/wormhole-sdk-ts", "c0dbf3498e9eb5dc40d2441ac61567a89d6fbde9", "Apache-2.0"),
    "across": ("across-protocol/contracts", "b1c4e86225420df5cb8d03042526622aca80fe61", "BUSL-1.1; change to GPL-3.0-or-later on 2027-07-27 (or earlier per license)"),
    "op_registry": ("ethereum-optimism/superchain-registry", "009155d5f96df7fe564fd37e2751d9dd0480e0ed", "MIT"),
    "arbitrum": ("OffchainLabs/arbitrum-sdk", "cbb96c6f7f84d71bdef65d0fd9d3d7275a236711", "Apache-2.0"),
}

FILES = {
    "brian": [f"data/{chain}/combined/combinedAccountLabels.json" for chain in
              ("etherscan", "arbiscan", "avalanche", "bscscan", "ftmscan", "optimism", "polygonscan")],
    "daws": ["data/csv/accounts.csv"],
    "tornado": ["networkConfig.js"],
    "railgun": ["src/models/network-config.ts"],
    "hop": ["packages/sdk/src/addresses/mainnet.ts"],
    "wormhole": ["core/base/src/constants/contracts/tokenBridge.ts"],
    "across": ["broadcast/deployed-addresses.json"],
    "op_registry": ["superchain/extra/addresses/addresses.json"],
    "arbitrum": ["packages/sdk/src/lib/dataEntities/networks.ts"],
}


def collect(refresh: bool = False) -> None:
    target = ROOT / "data/labels"
    target.mkdir(parents=True, exist_ok=True)
    sources = []
    for source_id, (repo, revision, license_name) in PINS.items():
        license_bytes, license_ref = github_file(repo, revision, "LICENSE")
        license_path = target / "licenses" / (source_id + ".txt")
        license_path.parent.mkdir(exist_ok=True)
        license_path.write_bytes(license_bytes)
        source = {"source_id": source_id, "name": repo, "revision": revision, "license": license_name,
                  "license_ref": license_ref, "url": f"https://github.com/{repo}/tree/{revision}", "files": []}
        for path in FILES[source_id]:
            payload, raw_ref = github_file(repo, revision, path)
            source["files"].append({"path": path, "raw_ref": raw_ref,
                                    "url": f"https://raw.githubusercontent.com/{repo}/{revision}/{path}",
                                    "sha256": hashlib.sha256(payload).hexdigest()})
        sources.append(source)
        print(source_id, len(source["files"]), flush=True)
    # Freeze shared inputs for offline reproducibility while concurrent processes continue.
    local_files = []
    for path in ("data/addresses.csv", "data/ledger.csv"):
        payload = (ROOT / path).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        raw = RAW / "local" / (digest + ".csv.gz")
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(gzip.compress(payload, mtime=0))
        local_files.append({"path": path, "raw_ref": str(raw.relative_to(ROOT)), "sha256": digest,
                            "url": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML"})
    sources.append({"source_id": "ofac", "name": "OFAC ledger / data/addresses.csv", "revision": "local input SHA-256",
                    "license": "US government sanctions facts; no third-party dataset license asserted",
                    "url": "https://ofac.treasury.gov/sanctions-list-service", "files": local_files})
    tron_files = []
    for path in sorted((ROOT / "data/raw/tron/labels").glob("*.json.gz")):
        try:
            payload = gzip.decompress(path.read_bytes())
            data = json.loads(payload)
        except (OSError, ValueError):
            continue
        digest = hashlib.sha256(payload).hexdigest()
        raw = RAW / "tron" / (digest + ".json.gz")
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(gzip.compress(payload, mtime=0))
        tron_files.append({"path": str(path.relative_to(ROOT)), "raw_ref": str(raw.relative_to(ROOT)),
                           "sha256": digest, "url": data.get("request", {}).get("url", ""), "envelope": True})
    sources.append({"source_id": "tronscan", "name": "TronScan public account API", "revision": "timestamped responses",
                    "license": "No explicit open-data redistribution license found; public API facts only",
                    "url": "https://apilist.tronscanapi.com/api/account", "files": tron_files})
    # Bounded, explicitly named BTC clusters. These are heuristic cluster leads, not hot/deposit claims.
    wallets = ("Binance.com", "Bitstamp.net", "Bitfinex.com", "Kraken.com", "Bittrex.com", "Poloniex.com",
               "Huobi.com", "BTC-e.com", "BitMEX.com", "HelixMixer", "BitcoinFog", "BitMixer.io")
    wallet_files = []
    for wallet in wallets:
        url = f"https://www.walletexplorer.com/api/1/wallet-addresses?wallet={wallet}&from=0&count=100"
        try:
            payload, raw_ref = fetch(url, refresh=refresh)
            wallet_files.append({"path": wallet, "raw_ref": raw_ref, "url": url,
                                 "sha256": hashlib.sha256(payload).hexdigest()})
            print("walletexplorer", wallet, json.loads(payload).get("found"), flush=True)
        except Exception as exc:
            print("walletexplorer", wallet, type(exc).__name__, flush=True)
        time.sleep(0.4)
    faq, faq_ref = fetch("https://www.walletexplorer.com/info", refresh=refresh)
    api, api_ref = fetch("https://www.walletexplorer.com/api", refresh=refresh)
    sources.append({"source_id": "walletexplorer", "name": "WalletExplorer.com public cluster API",
                    "revision": "timestamped API snapshots; first 100 addresses per requested cluster only",
                    "license": "No explicit open-data redistribution license found; public API facts only",
                    "license_ref": api_ref, "caveats_ref": faq_ref,
                    "url": "https://www.walletexplorer.com/api", "files": wallet_files})
    uniswap_files = []
    for network in ("ethereum", "arbitrum", "optimism", "polygon", "base", "bsc", "avalanche"):
        url = f"https://docs.uniswap.org/contracts/v3/reference/deployments/{network}-deployments"
        try:
            payload, raw_ref = fetch(url, refresh=refresh)
            uniswap_files.append({"path": network, "raw_ref": raw_ref, "url": url,
                                    "sha256": hashlib.sha256(payload).hexdigest()})
        except Exception as exc:
            print("uniswap", network, type(exc).__name__, flush=True)
    sources.append({"source_id": "uniswap", "name": "Uniswap official v3 deployment documentation",
                    "revision": "timestamped documentation snapshots", "license": "No license established for these web pages; factual contract addresses only",
                    "url": "https://docs.uniswap.org/contracts/v3/reference/deployments", "files": uniswap_files})
    for source_id, name, urls in (
        ("sun", "SUN.io official contract documentation", [
            "https://docs.sun.io/protocols/sunswap-v2/reference/contract",
            "https://docs.sun.io/protocols/sunswap-v3/reference/contract",
            "https://docs.sun.io/protocols/universal-router/reference/contract"]),
        ("stargate", "Stargate official mainnet contract documentation", [
            "https://stargateprotocol.gitbook.io/stargate/developers/contract-addresses/mainnet.md"]),
        ("base", "Base official network contract documentation", [
            "https://docs.base.org/base-chain/network-information/base-contracts"]),
        ("avalanche_bridge", "Avalanche official bridge FAQ", [
            "https://support.avax.network/en/articles/6092559-avalanche-bridge-faq"]),
    ):
        files = []
        for url in urls:
            payload, raw_ref = fetch(url, refresh=refresh)
            files.append({"path": url.split("/protocols/")[-1] if source_id == "sun" else url.rsplit("/", 1)[-1],
                          "raw_ref": raw_ref, "url": url, "sha256": hashlib.sha256(payload).hexdigest()})
        sources.append({"source_id": source_id, "name": name, "revision": "timestamped documentation snapshots",
                        "license": "No license established for these web pages; factual contract addresses only",
                        "url": urls[0], "files": files})
    explorer_files = []
    for address, expected, role in (("0xf1da173228fcf015f43f3ea15abbb51f0d8f1123", "eXch: Hot wallet", "unknown_service"),
                                    ("0x1681d536b8a47c01d7ea07f0d80a2eb10e7ce842", "eXch.sc 2", "unknown_service"),
                                    ("0xd9fc01e6aad73ec74ca30b84e994a8e9631c7bf9", "Bitget Deposit: 0xd9Fc01E6Aad73EC74ca30b84E994A8E9631C7bF9", "cex_deposit")):
        url = "https://etherscan.io/address/" + address
        payload, raw_ref = fetch(url, refresh=refresh)
        explorer_files.append({"path": address, "raw_ref": raw_ref, "url": url, "expected_label": expected, "class": role,
                               "sha256": hashlib.sha256(payload).hexdigest()})
    sources.append({"source_id": "etherscan_public", "name": "Etherscan public Ethereum address name tags",
                    "revision": "timestamped public address pages",
                    "license": "No open-data redistribution license established; factual name tags only",
                    "url": "https://etherscan.io/", "files": explorer_files})
    thor_url = "https://gateway.liquify.com/chain/thorchain_api/thorchain/inbound_addresses"
    thor_bytes, thor_ref = fetch(thor_url, refresh=refresh)
    documentation, documentation_ref = fetch("https://dev.thorchain.org/concepts/connecting-to-thorchain.html", refresh=refresh)
    sources.append({"source_id": "thorchain", "name": "THORChain inbound-address API via documented Liquify gateway",
                    "revision": "timestamped current-vault/router snapshot",
                    "license": "No open-data redistribution license established for the API response; factual addresses only",
                    "url": thor_url, "documentation_ref": documentation_ref,
                    "files": [{"path": "inbound_addresses", "raw_ref": thor_ref, "url": thor_url,
                               "sha256": hashlib.sha256(thor_bytes).hexdigest()}]})
    for source in sources:
        for file in source["files"]:
            key = hashlib.sha256(file["url"].encode()).hexdigest()
            meta = RAW / "requests" / (key + ".json")
            if meta.exists() and not file.get("envelope") and source["source_id"] != "ofac":
                file["retrieved_at"] = json.loads(meta.read_text())["retrieved_at"]
    manifest = {"collected_at": datetime.now(timezone.utc).isoformat(), "sources": sources}
    serialized = (json.dumps(manifest, indent=2) + "\n").encode()
    archive = RAW / "manifests" / (hashlib.sha256(serialized).hexdigest() + ".json.gz")
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(gzip.compress(serialized, mtime=0))
    (target / "sources.json").write_bytes(serialized)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch mutable APIs and web pages; pinned GitHub data remain cached")
    args = parser.parse_args()
    collect(args.refresh)
