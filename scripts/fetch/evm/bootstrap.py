"""Fetch pinned list DATA, never upstream code. Lists live on the lists branch."""
import csv
from pathlib import Path
import re

from client import Client, ROOT, RAW, save_json
from chains import TICKERS

REPO = "https://api.github.com/repos/0xB10C/ofac-sanctioned-digital-currency-addresses"
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")


def bootstrap(client, target=ROOT / "data/bootstrap/fetch_evm.csv"):
    commit, commit_ref = client.request("bootstrap", REPO + "/commits/lists")
    revision = commit["sha"]
    tree, tree_ref = client.request("bootstrap", REPO + f"/git/trees/{revision}", {"recursive": 1})
    rows = {}
    sources = []
    for item in tree["tree"]:
        path = item["path"]
        match = re.fullmatch(r"(?:lists/)?sanctioned_addresses_([A-Z0-9]+)\.txt", path)
        if not match or match[1] not in TICKERS:
            continue
        ticker = match[1]
        url = f"https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/{revision}/{path}"
        content, ref = client.request("bootstrap", url)
        if not isinstance(content, str):
            raise ValueError("Bootstrap list must be text")
        for line in content.splitlines():
            address = line.strip()
            if not ADDRESS.fullmatch(address):
                continue  # USDT/USDC also list non-EVM address formats.
            chain = TICKERS[ticker]
            row = rows.setdefault((chain, address.lower()), {"chain": chain, "address": address.lower(), "tickers": set(), "source_url": url, "raw_ref": ref})
            row["tickers"].add(ticker)
        sources.append({"ticker": ticker, "source_url": url, "raw_ref": ref})
    # Preserve historical coverage, including delisted pool contracts. The current
    # SDN-derived snapshot alone intentionally no longer contains Tornado Cash.
    historical, historical_ref = client.request("bootstrap", REPO + "/commits", {"sha": "lists", "until": "2025-03-20T23:59:59Z", "per_page": 1})
    historical_revision = historical[0]["sha"]
    url = f"https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/{historical_revision}/sanctioned_addresses_ETH.txt"
    content, ref = client.request("bootstrap", url)
    sources.append({"ticker": "ETH", "scope": "historical_pre_delisting", "source_url": url, "raw_ref": ref, "commit_raw_ref": historical_ref})
    for line in content.splitlines():
        address = line.strip().lower()
        if ADDRESS.fullmatch(address):
            rows.setdefault(("eth", address), {"chain": "eth", "address": address, "tickers": {"ETH"}, "source_url": url, "raw_ref": ref})
    if not rows:
        raise ValueError("No EVM bootstrap rows found; do not silently replace with an empty input")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["chain", "address", "tickers", "source_url", "raw_ref"])
        writer.writeheader()
        for key, row in sorted(rows.items()):
            writer.writerow({**row, "tickers": ";".join(sorted(row["tickers"]))})
    save_json(RAW / "bootstrap/provenance.json.gz", {"revision": revision, "historical_revision": historical_revision, "commit_ref": commit_ref, "tree_ref": tree_ref, "sources": sources, "rows": len(rows), "distinct_addresses": len({a for _, a in rows})})
    return target


if __name__ == "__main__":
    print(bootstrap(Client()))
