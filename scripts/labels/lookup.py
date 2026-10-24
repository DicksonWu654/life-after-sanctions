"""Fast, read-only destination labels. Missing labels return []; no ownership inference.

    from scripts.labels.lookup import label
    rows = label("ethereum", "0x...")

CLI: .venv/bin/python scripts/labels/lookup.py ETH 0x...
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

try:
    from .policy import normalize_address, normalize_chain
except ImportError:
    from policy import normalize_address, normalize_chain

DATABASE = Path(__file__).resolve().parents[2] / "data/labels/labels.sqlite"


def label(chain: str | int, address: str) -> list[dict[str, str]]:
    """Return all source claims for this exact chain/address; conflicts remain visible.

    Accepts numeric EVM chain IDs, repo tickers and common aliases. BNB remains BNB
    (Beacon chain), and is never silently merged into BSC. Base58 addresses remain
    case-sensitive. A missing database raises FileNotFoundError, not an empty result.
    """
    chain = normalize_chain(chain)
    address = normalize_address(chain, address)
    if not DATABASE.is_file():
        raise FileNotFoundError(f"Build the label index first: {DATABASE}")
    # A connection per call is inexpensive with an indexed local file and is thread-safe.
    with sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM labels WHERE chain=? AND address_normalized=? "
            "ORDER BY CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, source_id, label",
            (chain, address),
        ).fetchall()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chain")
    parser.add_argument("address")
    args = parser.parse_args()
    print(json.dumps(label(args.chain, args.address), indent=2))
