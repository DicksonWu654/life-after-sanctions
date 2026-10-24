"""Validate provenance, normalization, source records, and indexed lookups offline."""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
import random
import re
import sqlite3
import time
from functools import lru_cache

try:
    from .build import FIELDS, OUT, Tables, object_at, read_raw
    from .lookup import label
    from .policy import BASE_CLASSES, CLASSES, EVM, classify, normalize_address, normalize_chain
    from .sources import ROOT
except ImportError:
    from build import FIELDS, OUT, Tables, object_at, read_raw
    from lookup import label
    from policy import BASE_CLASSES, CLASSES, EVM, classify, normalize_address, normalize_chain
    from sources import ROOT

SEED = 20261023


@lru_cache(maxsize=256)
def raw_text(ref: str):
    return gzip.decompress((ROOT / ref).read_bytes()).decode("utf-8-sig")


@lru_cache(maxsize=32)
def raw_json(ref: str):
    return json.loads(raw_text(ref))


@lru_cache(maxsize=4)
def raw_csv(ref: str):
    return list(csv.DictReader(io.StringIO(raw_text(ref))))


@lru_cache(maxsize=16)
def raw_tables(ref: str):
    parser = Tables()
    parser.feed(raw_text(ref))
    return parser.tables


def evidence(row: dict) -> str:
    """Check the specific source record, independently of the row-generation loop."""
    locator = json.loads(row["evidence_locator"])
    ref = row["source_ref"]
    kind = locator["kind"]
    address = row["address_normalized"]
    chain = row["chain"]

    def assert_address(value: str):
        assert normalize_address(chain, value) == address, (row["label"], "source address mismatch", value)

    if kind == "json_label":
        record = raw_json(ref)[locator["key"]]
        assert_address(locator["key"])
        assert record["name"] == row["label"] == row["entity_name"]
        assert classify(record["name"], record["labels"])[0] == row["class"]
        return json.dumps(record, ensure_ascii=False)
    if kind == "csv_label":
        records = [raw_csv(ref)[index] for index in locator["indexes"]]
        for record in records:
            assert_address(record["address"])
            assert normalize_chain(record["chainId"]) == chain
            assert record["nameTag"] == row["label"] == row["entity_name"]
        tags = sorted({record["label"] for record in records})
        assert classify(row["label"], tags)[0] == row["class"]
        return json.dumps({"chainId": records[0]["chainId"], "address": records[0]["address"],
                           "nameTag": records[0]["nameTag"], "labels": tags}, ensure_ascii=False)
    if kind == "ofac":
        record = raw_csv(ref)[locator["index"]]
        assert_address(record["address_normalized"])
        assert record["chain"] == chain
        members = [member for member in raw_csv(locator["ledger_ref"])
                   if member["sdn_uid"] == locator["entity_uid"] and member["address_normalized"] == address]
        assert members and all(member["sdn_name"] == row["entity_name"] for member in members)
        assert locator["entity_uid"] in record["all_entity_uids"].split(";")
        assert row["class"] in ("other_sanctioned", "mixer")
        return json.dumps({"address": address, "chain": chain, "sdn_uid": locator["entity_uid"],
                           "sdn_name": members[0]["sdn_name"], "current_in_sdn": members[0].get("current_in_sdn"),
                           "listed_date": members[0]["listed_date"], "delisted_date": members[0]["delisted_date"]}, ensure_ascii=False)
    if kind == "walletexplorer":
        payload = raw_json(ref)
        record = payload["addresses"][locator["index"]]
        assert_address(record["address"])
        assert payload["found"] and payload["label"] == row["label"] == row["entity_name"]
        assert chain == "BTC" and row["confidence"] == "low"
        return json.dumps({"label": payload["label"], "wallet_id": payload["wallet_id"], "address": record["address"]})
    if kind == "html_table":
        table = raw_tables(ref)[locator["table"]]
        record = table[locator["row"]]
        assert_address(record[locator["column"]])
        assert record[0] == locator["contract"] and locator["contract"] in row["label"]
        return json.dumps({"header": table[0], "row": record, "column": locator["column"]})
    if kind == "across":
        record = raw_json(ref)["chains"][locator["chain_id"]]["contracts"][locator["field"]]
        assert_address(record["address"])
        assert normalize_chain(locator["chain_id"]) == chain
        return json.dumps({"chain_id": locator["chain_id"], "contract": locator["field"], **record})
    if kind == "op_registry":
        value = raw_json(ref)[locator["chain_id"]][locator["field"]]
        assert_address(value)
        assert chain == "ETH"
        return json.dumps({"destination_chain_id": locator["chain_id"], "contract": locator["field"], "Ethereum_address": value})
    if kind == "tronscan":
        payload = raw_json(ref)["response"]
        assert_address(payload["address"])
        assert payload[locator["field"]] == row["label"]
        return json.dumps({"address": payload["address"], locator["field"]: row["label"]})
    if kind == "thorchain":
        record = raw_json(ref)[locator["index"]]
        assert_address(record[locator["field"]])
        assert normalize_chain(record["chain"]) == chain and row["class"] == "bridge"
        return json.dumps({"chain": record["chain"], locator["field"]: record[locator["field"]], "halted": record.get("halted")})
    text = raw_text(ref)
    if kind == "html_title":
        title = re.search(r"<title[^>]*>([\s\S]*?)</title>", text, re.I)
        assert title and " ".join(title[1].split()) == locator["title"]
        assert locator["title"].split(" | Address:")[0] == row["label"]
        assert address in row["source_url"] and address in text.lower() and chain == "ETH"
        return locator["title"]
    if kind == "official_link":
        assert 'href="' + locator["href"] + '"' in text
        assert address in locator["href"].lower()
        assert (chain == "ETH" and "etherscan.io/address/" in locator["href"]) or (chain == "AVAX" and "avax.network/c-chain/address/" in locator["href"])
        return locator["href"]
    if kind in ("tornado_pool", "tornado_router"):
        marker = re.search(r"\bnetId" + str(locator["network"]) + r":\s*\{", text)
        assert marker and normalize_chain(locator["network"]) == chain
        block, _ = object_at(text, marker.start())
        if kind == "tornado_pool":
            marker = re.search(r"\b" + re.escape(locator["asset"]) + r":\s*\{\s*instanceAddress:", block)
            assert marker
            asset, _ = object_at(block, marker.start())
            match = re.search(r"'" + re.escape(locator["denomination"]) + r"':\s*'(0x[0-9a-fA-F]{40})'", asset)
        else:
            match = re.search(r"'" + re.escape(locator["key"]) + r"':\s*'(0x[0-9a-fA-F]{40})'", block)
        assert match
        assert_address(match[1])
        return json.dumps({"network": locator["network"], "source_literal": match[0]})
    if kind == "railgun":
        marker = re.search(r"export const " + re.escape(locator["field"]) + r"\b[^=]*=\s*\{", text)
        assert marker
        block, _ = object_at(text, marker.start())
        match = re.search(r"\[NetworkName\." + re.escape(locator["network"]) + r"\]:\s*'(0x[0-9a-fA-F]{40})'", block)
        assert match
        assert_address(match[1])
        return locator["field"] + ": " + match[0]
    if kind == "hop":
        block, _ = object_at(text, text.index("bridges:"))
        marker = re.search(r"^    (?:'" + re.escape(locator["asset"]) + r"'|" + re.escape(locator["asset"]) + r"):\s*\{", block, re.M)
        assert marker
        asset, _ = object_at(block, marker.start())
        marker = re.search(r"^      " + re.escape(locator["network"]) + r":\s*\{", asset, re.M)
        assert marker
        network, _ = object_at(asset, marker.start())
        match = re.search(r"\b" + re.escape(locator["field"]) + r":\s*'(0x[0-9a-fA-F]{40})'", network)
        assert match
        assert_address(match[1])
        return json.dumps({"asset": locator["asset"], "network": locator["network"], "source_literal": match[0]})
    if kind == "wormhole":
        mainnet = text.split('"Testnet"')[0]
        match = re.search(r'\["' + re.escape(locator["network"]) + r'",\s*"([^"\n]+)"\]', mainnet)
        assert match
        assert_address(match[1])
        return "Mainnet " + match[0]
    if kind == "arbitrum":
        block, _ = object_at(text, text.index("const " + locator["object"]))
        match = re.search(r"\b" + re.escape(locator["field"]) + r":\s*'(0x[0-9a-fA-F]{40})'", block)
        assert match
        assert_address(match[1])
        return locator["object"] + ": " + match[0]
    if kind == "markdown_line":
        lines = text.splitlines()
        line = lines[locator["line"]]
        heading = next(line[4:].replace("\u200b", "").strip() for line in reversed(lines[:locator["line"]]) if line.startswith("### "))
        assert heading == locator["heading"] and locator["field"] in line
        assert address in line.lower()
        return heading + ": " + line
    raise AssertionError("Unhandled source locator: " + kind)


def summarize(rows: list[dict]) -> dict:
    sources = json.loads((OUT / "sources.json").read_text())
    by_chain = {}
    for chain in sorted({row["chain"] for row in rows}):
        members = [row for row in rows if row["chain"] == chain]
        by_chain[chain] = {"label_rows": len(members),
                           "unique_addresses": len({row["address_normalized"] for row in members}),
                           "classes": {role: sum(row["class"] == role for row in members) for role in BASE_CLASSES}}
    return {"collected_at": sources["collected_at"], "label_rows": len(rows),
            "unique_chain_addresses": len({(row["chain"], row["address_normalized"]) for row in rows}),
            "chain_count": len(by_chain), "by_chain": by_chain,
            "by_class": {role: sum(row["class"] == role for row in rows) for role in BASE_CLASSES},
            "by_source": {source["source_id"]: {"label_rows": sum(row["source_id"] == source["source_id"] for row in rows),
                            "unique_chain_addresses": len({(row["chain"], row["address_normalized"]) for row in rows if row["source_id"] == source["source_id"]})}
                           for source in sources["sources"]},
            "by_confidence": dict(collections.Counter(row["confidence"] for row in rows)),
            "csv_sha256": hashlib.sha256((OUT / "labels.csv").read_bytes()).hexdigest()}


def validate(write: bool) -> dict:
    manifest = json.loads((OUT / "sources.json").read_text())
    with (OUT / "labels.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == FIELDS
        rows = list(reader)
    assert len(rows) >= 30
    source_files = {}
    for source in manifest["sources"]:
        for file in source["files"]:
            read_raw(file)  # Cryptographic integrity check, including files that yielded zero labels.
            source_files[(source["source_id"], file["raw_ref"])] = file
    identities = set()
    for row in rows:
        assert row["class"] in CLASSES and row["confidence"] in {"high", "medium", "low"}
        assert row["raw_ref"] == row["source_ref"] and row["source_url"] and row["license"]
        assert (row["source_id"], row["source_ref"]) in source_files
        assert row["chain"] == normalize_chain(row["chain"])
        assert row["address_normalized"] == normalize_address(row["chain"], row["address_normalized"])
        assert not re.search(r"(?i)(?:apikey|api_key)=", row["source_url"])
        identity = tuple(row[field] for field in FIELDS)
        assert identity not in identities
        identities.add(identity)
        evidence(row)
    # All OFAC input chain/address keys survive, including untrackable and historical entries.
    ofac = next(source for source in manifest["sources"] if source["source_id"] == "ofac")
    expected = {(row["chain"], row["address_normalized"]) for row in raw_csv(ofac["files"][0]["raw_ref"])}
    actual = {(row["chain"], row["address_normalized"]) for row in rows if row["source_id"] == "ofac"}
    assert expected == actual
    # Meaningful role/identity regressions, not merely tests mirroring generated rows.
    assert classify("Bitcasino.io: Hot Wallet", ["exchange"])[0] == "unknown_service"
    assert classify("Binance: Deposit Funder", ["binance", "exchange"])[0] == "unknown_service"
    assert classify("Binance: Hot Wallet 1", ["binance", "exchange"])[0] == "cex_hot"
    assert classify("Bitget Dep: 0xd9Fc01E6Aad73EC74ca30b84E994A8E9631C7bF9", ["bitget"])[0] == "cex_deposit"
    assert classify("Binance Dep: 0x29e3ef87c3da0989c72b5c19e43f52f012b70b69", ["bilaxy"])[0] == "unknown_service"
    assert classify("Tornado.Cash: TORN Token", ["tornado-cash"])[0] != "mixer"
    assert classify("Hop Protocol: ETH Bonder", ["bridge", "hop-protocol"])[0] != "bridge"
    assert classify("Victim of Exploit", ["exploit", "phish-hack"]) is None
    assert normalize_chain("BNB") == "BNB" and normalize_chain(56) == "BSC"
    assert normalize_address("TRX", "41a614f803b6fd780986a42c78ec9c7f77e6ded13c") == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    assert label("ETH", "0x" + "0" * 40) == []
    assert label("ETH", "anything' OR 1=1 --") == []
    tornado = "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc"
    assert any(row["class"] == "mixer" for row in label("ethereum", tornado.upper()))
    assert not label("TRX", tornado)
    tron_router = "TNJVzGqKBWkJxJB5XYSqGAwUTV15U24pPq"
    assert any(row["class"] == "dex" for row in label("tron", tron_router))
    assert not label("tron", tron_router.lower())
    assert not any(row["source_id"] == "sun" for row in label("TRX", "TYMjxCXfqLpMWW1QToP6hbcjpion7EE25p"))
    with sqlite3.connect(f"file:{OUT / 'labels.sqlite'}?mode=ro", uri=True) as connection:
        query_plan = [list(row) for row in connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM labels WHERE chain=? AND address_normalized=?", ("ETH", tornado))]
        assert any("labels_chain_address" in str(item) for item in query_plan)
    random_indexes = random.Random(SEED).sample(range(len(rows)), 30)
    spot_checks = []
    for number, index in enumerate(random_indexes, 1):
        row = rows[index]
        spot_checks.append({"number": number, "csv_data_row": index + 1, "chain": row["chain"],
                            "address_normalized": row["address_normalized"], "label": row["label"], "class": row["class"],
                            "confidence": row["confidence"], "source_id": row["source_id"], "source_url": row["source_url"],
                            "source_ref": row["source_ref"], "evidence_locator": row["evidence_locator"],
                            "source_evidence": evidence(row), "result": "PASS: exact source record and conservative class mapping"})
    # Extra source-balanced checks supplement the uniform sample (never replace it).
    supplemental = []
    for source_id in sorted({row["source_id"] for row in rows}):
        row = next(row for row in rows if row["source_id"] == source_id)
        supplemental.append({"source_id": source_id, "chain": row["chain"], "address_normalized": row["address_normalized"],
                             "label": row["label"], "class": row["class"], "source_ref": row["source_ref"],
                             "evidence": evidence(row), "result": "PASS"})
    start = time.perf_counter()
    for index in random_indexes:
        row = rows[index]
        assert row in label(row["chain"], row["address_normalized"])
    elapsed = time.perf_counter() - start
    summary = summarize(rows)
    summary["validation"] = {"all_source_records_checked": len(rows), "raw_files_checked": len(source_files),
                             "spot_check_seed": SEED, "random_spot_checks": 30,
                             "supplemental_source_checks": len(supplemental), "ofac_chain_addresses_preserved": len(expected),
                             "lookup_query_plan": query_plan}
    if write:
        (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (OUT / "supplemental_checks.json").write_text(json.dumps(supplemental, indent=2) + "\n")
        with (OUT / "spot_checks.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(spot_checks[0]))
            writer.writeheader()
            writer.writerows(spot_checks)
    else:
        assert json.loads((OUT / "summary.json").read_text()) == summary, "Summary has drifted"
        stored = list(csv.DictReader((OUT / "spot_checks.csv").open()))
        assert stored == [{key: str(value) for key, value in row.items()} for row in spot_checks], "Spot checks have drifted"
    return {"status": "passed", **summary["validation"], "thirty_lookup_seconds": round(elapsed, 4)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate generated reports without writing")
    args = parser.parse_args()
    print(json.dumps(validate(not args.check), indent=2))
