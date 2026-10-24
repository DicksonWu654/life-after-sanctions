#!/usr/bin/env python3
"""Offline, rerunnable inflow analysis. Writes only this analysis's three output paths.

Run: .venv/bin/python -B scripts/analysis/inflows.py
Check the saved input snapshot: same command with --check.
New files are ignored by --check; changed snapshot inputs require a fresh run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
import statistics
import sys
import tempfile
import zlib
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.prices import price as prices
from scripts.labels.policy import normalize_address, normalize_chain

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
OUTPUT_JSON = ROOT / "results/inflows.json"
OUTPUT_CSV = ROOT / "data/derived/inflows.csv"
OUTPUT_DOC = ROOT / "docs/analysis/INFLOWS.md"
VALUE_TIME = "at each transfer; latest saved hourly observation within 2h, otherwise daily within 2d"
SCRIPT = "scripts/analysis/inflows.py"
NATIVE = {"ETH": "ETH", "ETC": "ETC", "ARB": "ETH", "BASE": "ETH", "OP": "ETH",
          "BSC": "BNB", "POLYGON": "POL", "AVAX": "AVAX", "BTC": "BTC", "BCH": "BCH",
          "BSV": "BSV", "LTC": "LTC", "DOGE": "DOGE", "DASH": "DASH", "ZEC": "ZEC",
          "XVG": "XVG", "TRX": "TRX", "SOL": "SOL", "XRP": "XRP", "BNB": "BNB"}
# Contract identities, never token symbols supplied by a sender. The core stablecoin
# identities agree with scripts/fetch/evm/chains.py and the Tron fetcher. Additional
# widely used identities are explicit here so a missing quote is not called spam.
TOKENS = {
 "ETH": {
  "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
  "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
  "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "ETH",
  "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
  "0xa47c8bf37f92abed4a126bda807a7b7498661acd": "UST",
  "0x674c6ad92fd080e4004b2312b45f796a192d27a0": "USDN",
  "0x5a98fcbea516cf06857215779fd812ca3bef1b32": "LDO",
  "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
  "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": "MATIC",
  "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": "SHIB",
  "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": "UNI",
  "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": "WSTETH",
  "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "STETH",
  "0xd533a949740bb3306d119cc777fa900ba034cd52": "CRV",
  "0x04fa0d235c4abf4bcf4787af4cf447de572ef828": "UMA",
  "0x408e41876cccdc0f92210600ef50372656052a38": "REN",
  "0x77777feddddffc19ff86db637967013e6c6a116c": "TORN",
 },
 "TRX": {"TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "USDT",
         "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8": "USDC",
         "TEk2J6HjyBKu47ai6ScwkbchfkWnPWuckM": "TUSD"},
 "ARB": {"0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": "USDT",
         "0xaf88d065e77c8cc2239327c5edb3a432268e5831": "USDC",
         "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8": "USDC",
         "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": "ETH",
         "0x912ce59144191c1204e64559fe8253a0e49e6548": "ARB"},
 "BSC": {"0x55d398326f99059ff775485246999027b3197955": "USDT",
         "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC"},
 "BASE": {"0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "USDC"},
 "OP": {"0x0b2c639c533813f4aa9d7837caf62653d097ff85": "USDC",
        "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": "USDT"},
 "POLYGON": {"0xc2132d05d31c914a87c6611c10748aeb04b58e8f": "USDT",
             "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": "USDC"},
 "SOL": {"Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
         "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC"},
}
EXPLORERS = {"ETH": "https://etherscan.io/tx/", "ARB": "https://arbiscan.io/tx/",
 "BSC": "https://bscscan.com/tx/", "BASE": "https://basescan.org/tx/",
 "OP": "https://optimistic.etherscan.io/tx/", "POLYGON": "https://polygonscan.com/tx/",
 "ETC": "https://etc.blockscout.com/tx/", "AVAX": "https://snowtrace.io/tx/",
 "BTC": "https://mempool.space/tx/", "TRX": "https://tronscan.org/#/transaction/",
 "XRP": "https://xrpscan.com/tx/", "SOL": "https://solscan.io/tx/",
 "BCH": "https://blockchair.com/bitcoin-cash/transaction/", "LTC": "https://blockchair.com/litecoin/transaction/",
 "DASH": "https://blockchair.com/dash/transaction/", "DOGE": "https://blockchair.com/dogecoin/transaction/",
 "ZEC": "https://blockchair.com/zcash/transaction/", "BSV": "https://whatsonchain.com/tx/",
 "BNB": "https://explorer.bnbchain.org/tx/", "XVG": "https://verge-blockchain.info/tx/"}
BOUNDS = [(0, 1), (1, 7), (7, 30), (30, 90), (90, 365), (365, 730), (730, 1095), (1095, None)]
FIELDS = ["chain", "address", "recipient_scope", "sdn_uids", "sdn_names", "programs", "listed_date",
 "delisted_date", "period", "time_utc", "days_after_T", "designation_day_ambiguous", "hash", "event_id",
 "kind", "asset", "symbol", "amount", "amount_convention", "inflow_class", "classification_status",
 "classification_rule", "classification_confidence", "mimicked_counterparty", "usd", "valued_at",
 "price_asset", "price_usd", "price_source", "price_source_url", "price_raw_ref", "sender_addresses",
 "sender_basis", "sender_class", "sender_label_claims", "sender_label_raw_refs", "timeline_complete",
 "exchange_scale", "timeline_ref", "raw_ref", "source_url"]


def number(value, unit, valued_at=None):
    result = {"value": value, "unit": unit}
    if unit == "usd":
        result["valued_at"] = valued_at or VALUE_TIME
    return result


def parse_time(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def date_boundary(value):
    """OFAC date T starts at midnight ET; exact timestamps retain their time."""
    if not value:
        return None
    if len(value) == 10:
        return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), ET).astimezone(UTC)
    return parse_time(value)


def norm(chain, address):
    value = normalize_address(chain, str(address or ""))
    return value.removeprefix("bitcoincash:") if chain == "BCH" else value


def rel(path):
    return str(path.relative_to(ROOT))


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class JsonStream:
    """Standard-library JSON cursor; never reads a complete history into text."""
    def __init__(self, stream):
        self.stream = stream
        self.buffer = ""
        self.position = 0
        self.eof = False
        self.decoder = json.JSONDecoder()

    def more(self, size=1024 * 1024):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        chunk = self.stream.read(size)
        self.eof = not chunk
        self.buffer += chunk

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self.more()

    def expect(self, character):
        if self.peek() != character:
            raise ValueError(f"expected JSON delimiter {character}")
        self.position += 1

    def value(self):
        self.peek()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                # A numeric scalar may be cut at the chunk boundary.
                if end == len(self.buffer) and not self.eof:
                    self.more()
                    continue
                self.position = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                # Grow geometrically for a giant individual UTXO transaction;
                # retrying a growing multi-megabyte JSON value every 1 MiB is
                # quadratic even though the history itself is streamed.
                self.more(max(1024 * 1024, len(self.buffer) - self.position))


EVENT_FIELDS = {"hash", "event_id", "time_utc", "direction", "asset", "symbol", "amount", "from", "to",
                "input_addresses", "output_addresses", "counterparties", "input_value", "raw_ref", "kind",
                "event_type", "traceId", "logIndex", "transfer_ordinal", "success", "is_transfer"}


def load_compact_timeline(path, retain_events=True):
    """Parse each JSON event once, discarding bulky raw-input/output duplication."""
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        cursor = JsonStream(stream)
        timeline = {}
        cursor.expect("{")
        while cursor.peek() != "}":
            key = cursor.value()
            if not isinstance(key, str) or key in timeline:
                raise ValueError("invalid or duplicate timeline JSON key")
            cursor.expect(":")
            if key == "txs":
                cursor.expect("[")
                events = []
                hashes = set()
                while cursor.peek() != "]":
                    item = cursor.value()
                    if isinstance(item, dict) and item.get("hash"):
                        hashes.add(item["hash"])
                    if retain_events:
                        if isinstance(item, dict):
                            omitted = {"counterparties", "output_addresses"} if item.get("direction") == "in" else {"input_addresses"}
                            if "output_addresses" in item:
                                omitted.add("counterparties")
                            events.append({k: v for k, v in item.items() if k in EVENT_FIELDS and k not in omitted})
                        else:
                            events.append(item)
                    if cursor.peek() == "]":
                        break
                    cursor.expect(",")
                    if cursor.peek() == "]":
                        raise ValueError("trailing comma in txs")
                cursor.expect("]")
                timeline[key] = events
                timeline["_observed_transactions"] = len(hashes)
            else:
                timeline[key] = cursor.value()
            if cursor.peek() == "}":
                break
            cursor.expect(",")
            if cursor.peek() == "}":
                raise ValueError("trailing comma in timeline")
        cursor.expect("}")
        if cursor.peek():
            raise ValueError("trailing data after timeline")
        return timeline


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def asset_identity(chain, event):
    asset = norm(chain, event.get("asset"))
    native = NATIVE.get(chain)
    if native and asset.upper() in {native, "MATIC" if native == "POL" else native}:
        return native, True
    token = TOKENS.get(chain, {}).get(asset)
    return token, bool(token)


@lru_cache(maxsize=150000)
def quote(asset, timestamp):
    if not asset:
        return None, None, None, "", ""
    value, observed, source = prices.usd(asset, timestamp)
    if value is None:
        return None, None, None, "", ""
    resolved = prices.resolve_asset(asset)
    row = None
    for frequency in ("1h", "1d"):
        candidate = prices._lookup_rows(resolved["symbol"], frequency, prices.parse_time(timestamp))
        if candidate and candidate["valuation_time_utc"] == observed and candidate["source"] == source:
            row = candidate
            break
    return Decimal(str(value)), observed, source, row["source_url"] if row else "", row["raw_ref"] if row else ""


def signature(address):
    value = address[2:] if address.startswith("0x") else address
    return value[:4], value[-4:]


def classify(amount, usd_value, recognised, matched):
    if not recognised:
        return "poisoning", "off_recognised_token_list", "low"
    if matched and (amount == 0 or (usd_value is not None and usd_value < 1)):
        return "poisoning", "zero_or_below_1_usd_sender_matches_first_and_last_4_of_prior_real_counterparty", "medium"
    if amount == 0:
        return "dust", "zero_value_without_demonstrated_mimic", "high"
    if usd_value is None:
        return "", "recognised_asset_but_no_saved_transfer_time_price", "unresolved"
    if usd_value < 1:
        return "dust", "below_1_usd_at_transfer_time", "high"
    return "real", "at_least_1_usd_at_transfer_time_and_no_poisoning_rule", "high"


@lru_cache(maxsize=8)
def raw_document(path):
    with gzip.open(ROOT / path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def raw_item(reference):
    path, _, fragment = reference.partition("#")
    obj = raw_document(path)
    segments = fragment[1:].split("/") if fragment.startswith("/") else re.findall(r"[^.\[\]]+", fragment)
    for segment in segments:
        segment = segment.replace("~1", "/").replace("~0", "~") if fragment.startswith("/") else segment
        obj = obj[int(segment)] if isinstance(obj, list) else obj[segment]
    return obj


def senders(chain, event, address, diagnostics):
    if event.get("input_addresses") is not None:
        return sorted({norm(chain, a) for a in event["input_addresses"] if norm(chain, a) != address}), "utxo_input_addresses_not_people"
    if event.get("from"):
        return [norm(chain, event["from"])], "direct_from_address"
    if chain == "XRP":
        try:
            item = raw_item(event.get("raw_ref", ""))
            tx = item.get("tx", item.get("tx_json", {}))
            if tx.get("TransactionType") == "Payment" and tx.get("Destination") == address:
                return [tx["Account"]], "raw_xrp_payment_account"
        except (OSError, EOFError, ValueError, KeyError, TypeError, IndexError):
            diagnostics["xrp_sender_lookup_failed"] += 1
        return [], "balance_change_without_identified_direct_sender"
    # Token accounts are not owner wallets; do not count them as depositors.
    return [], "sender_not_in_saved_event"


def label_sender(chain, sender_list, timestamp, recipient, address_map, label_map):
    if not sender_list:
        return "unidentified_sender", [], []
    classes = set()
    claims = []
    refs = []
    for sender in sender_list:
        a = address_map.get((chain, sender))
        sanctioned_now = a and date_boundary(a["first_listed_date"]) <= timestamp and (
            not a.get("delisted_date") or timestamp < date_boundary(a["delisted_date"]))
        if sanctioned_now:
            classes.add("same_listed_entity" if set(a["sdn_uids"].split(";")) & set(recipient["sdn_uids"].split(";")) else "other_sanctioned")
            refs.append(a.get("raw_ref", ""))
            continue
        matched = []
        for claim in label_map.get((chain, sender), []):
            if claim.get("valid_from") and timestamp.date().isoformat() < claim["valid_from"][:10]:
                continue
            if claim.get("valid_to") and timestamp.date().isoformat() > claim["valid_to"][:10]:
                continue
            # Today's SDN label does not establish historical designation status.
            if claim["class"] == "other_sanctioned":
                continue
            mapped = {"cex_hot": "cex_withdrawal_labelled_hot_wallet", "cex_deposit": "cex_deposit_source"}.get(claim["class"], claim["class"])
            matched.append(mapped)
            claims.append({k: claim.get(k, "") for k in ("label", "class", "confidence", "source_url", "raw_ref", "valid_from", "valid_to")})
            refs.append(claim.get("raw_ref", ""))
        classes.update(matched or ["unlabelled"])
    return (next(iter(classes)) if len(classes) == 1 else "mixed_or_conflicting_labels"), claims, sorted(set(filter(None, refs)))


def example(row):
    return {k: row[k] for k in ("chain", "address", "hash", "source_url", "time_utc", "asset", "amount", "usd", "valued_at", "sender_addresses", "sender_basis", "sender_class", "classification_rule", "raw_ref", "price_raw_ref", "timeline_ref")}


def distinct_examples(rows, count=3, latest=False):
    ordered = sorted(rows, key=(lambda r: r["time_utc"]) if latest else (lambda r: float(r["usd"] or 0)), reverse=True)
    seen = set()
    output = []
    for row in ordered:
        if row["hash"] not in seen:
            output.append(example(row))
            seen.add(row["hash"])
        if len(output) == count:
            break
    return output


def usd_sum(rows):
    return float(sum((Decimal(r["usd"]) for r in rows), Decimal(0)).quantize(Decimal("0.01")))


def summary(rows):
    real = [r for r in rows if r["inflow_class"] == "real"]
    sender_keys = {(r["chain"], a) for r in real for a in r["sender_addresses"]}
    return {"inflow_events": number(len(rows), "events"),
            "real_events": number(len(real), "events"),
            "real_inflow_usd": number(usd_sum(real), "usd"),
            "dust_events": number(sum(r["inflow_class"] == "dust" for r in rows), "events"),
            "poisoning_events": number(sum(r["inflow_class"] == "poisoning" for r in rows), "events"),
            "unclassified_price_events": number(sum(not r["inflow_class"] for r in rows), "events"),
            "distinct_known_sender_addresses": number(len(sender_keys), "addresses"),
            "real_events_without_identified_sender": number(sum(not r["sender_addresses"] for r in real), "events"),
            "receiving_addresses": number(len({(r["chain"], r["address"]) for r in real}), "addresses"),
            "real_events_on_designation_date": number(sum(r["designation_day_ambiguous"] for r in real), "events"),
            "real_usd_after_designation_day": number(usd_sum(r for r in real if not r["designation_day_ambiguous"]), "usd"),
            "distinct_transactions": number(len({(r["chain"], r["hash"]) for r in real}), "transactions"),
            "raw_ref": sorted({r["raw_ref"].split("#", 1)[0] for r in rows if r.get("raw_ref")}),
            "price_raw_ref": sorted({ref.split("#", 1)[0] for r in real for ref in r["price_raw_ref"].split(";") if ref})}


def audit_example(row):
    """Independent raw checks for the small set of published example transfers."""
    try:
        item = raw_item(row["raw_ref"])
        chain = row["chain"]
        expected_hash = row["hash"].lower()
        observed_hash = item.get("hash", item.get("txid", item.get("transaction_id", item.get("transactionID", ""))))
        amount_matches = None
        recipient_matches = None
        if chain in {"ETH", "ARB", "BSC", "BASE", "OP", "ETC", "POLYGON", "AVAX"}:
            decimals = int(item.get("tokenDecimal", 18))
            amount_matches = Decimal(item["value"]) / (Decimal(10) ** decimals) == Decimal(row["amount"])
            recipient_matches = norm(chain, item.get("to")) == row["address"]
        elif chain == "TRX":
            if "token_info" in item:
                amount_matches = Decimal(item["value"]) / (Decimal(10) ** int(item["token_info"]["decimals"])) == Decimal(row["amount"])
                recipient_matches = item["to"] == row["address"]
            else:
                observed_hash = item.get("txID", observed_hash)
                contract = item["raw_data"]["contract"][0]["parameter"]["value"]
                amount_matches = Decimal(contract["amount"]) / Decimal(1000000) == Decimal(row["amount"])
                recipient_matches = norm(chain, contract["to_address"]) == row["address"]
        hash_matches = observed_hash.lower() == expected_hash
        price_refs_present = all((ROOT / ref.split("#")[0]).is_file() for ref in row["price_raw_ref"].split(";") if ref)
        return {"hash": row["hash"], "raw_hash_matches": hash_matches,
                "raw_amount_matches": amount_matches, "raw_recipient_matches": recipient_matches,
                "price_raw_files_present": price_refs_present,
                "status": "verified_hash_amount_recipient" if hash_matches and amount_matches and recipient_matches else "raw_hash_verified_amount_needs_chain_specific_review" if hash_matches else "needs_review",
                "raw_ref": row["raw_ref"]}
    except (OSError, EOFError, ValueError, KeyError, TypeError, IndexError, AttributeError, InvalidOperation) as exc:
        return {"hash": row["hash"], "status": "needs_review", "reason": type(exc).__name__, "raw_ref": row["raw_ref"]}


def grouped(rows, field):
    groups = defaultdict(list)
    for row in rows:
        keys = row[field] if field == "programs" else [row[field]]
        for key in keys:
            groups[key].append(row)
    return [{field: key, **summary(items)} for key, items in sorted(groups.items())]


def streak(months):
    integers = sorted({int(m[:4]) * 12 + int(m[5:7]) for m in months})
    best = run = 0
    previous = None
    for value in integers:
        run = run + 1 if previous is not None and value == previous + 1 else 1
        best = max(best, run)
        previous = value
    return best


def rank_addresses(rows, statuses):
    groups = defaultdict(list)
    for row in rows:
        if row["inflow_class"] == "real":
            groups[(row["chain"], row["address"])].append(row)
    output = []
    for key, items in groups.items():
        values = [float(r["usd"]) for r in items]
        total = sum(values)
        months = {r["time_utc"][:7] for r in items}
        dominant = max(values) / total
        pattern = "one_time_large_or_dominant" if dominant >= .8 else (
            "steady_drips" if len(items) >= 12 and len(months) >= 6 and statistics.median(values) <= 100 and dominant < .5 else "recurring_or_mixed")
        late = [r for r in items if float(r["days_after_T"]) >= 730]
        output.append({"chain": key[0], "address": key[1], "sdn_names": items[0]["sdn_names"],
          "programs": items[0]["programs"], "listed_date": items[0]["listed_date"],
          "delisted_date": items[0]["delisted_date"], "timeline_ref": items[0]["timeline_ref"],
          "timeline_complete": statuses[key]["complete"], "exchange_scale": statuses[key]["exchange_scale"],
          **summary(items), "first_real_inflow": min(r["time_utc"] for r in items),
          "last_real_inflow": max(r["time_utc"] for r in items),
          "latest_age_days": number(round(max(float(r["days_after_T"]) for r in items), 2), "days"),
          "active_months": number(len(months), "months"), "longest_consecutive_months": number(streak(months), "months"),
          "median_inflow_usd": number(round(statistics.median(values), 2), "usd"),
          "largest_inflow_usd": number(round(max(values), 2), "usd"),
          "largest_inflow_share": number(round(dominant, 6), "share"), "pattern": pattern,
          "two_year_plus_real_events": number(len(late), "events"),
          "two_year_plus_usd": number(round(sum(float(r["usd"]) for r in late), 2), "usd"),
          "examples": distinct_examples(items), "late_examples": distinct_examples(late, latest=True)})
    return sorted(output, key=lambda a: a["real_inflow_usd"]["value"], reverse=True)


def build(manifest_paths=None, generated_at=None):
    diagnostics = Counter({key: 0 for key in (
        "unreadable_or_partial_timeline_files_skipped", "nonledger_timeline_files_excluded",
        "duplicate_address_timeline_files_skipped", "tornado_timeline_files_reserved_for_tornado_job",
        "timeline_missing_designation_date", "malformed_events_skipped", "events_without_exact_time_skipped",
        "failed_or_nontransfer_events_excluded", "invalid_amount_events_skipped", "duplicate_inflow_events_skipped",
        "inflow_rows_with_missing_raw_evidence", "xrp_sender_lookup_failed")})
    input_manifest = []
    for path in [ROOT / "data/addresses.csv", ROOT / "data/ledger.csv", ROOT / "data/actions.csv",
                 ROOT / "data/labels/labels.csv", ROOT / SCRIPT, ROOT / "scripts/prices/price.py",
                 ROOT / "scripts/labels/policy.py", ROOT / "scripts/labels/lookup.py",
                 ROOT / "docs/DEFINITIONS.md", ROOT / "docs/DATA_CONTRACT.md"] + sorted((ROOT / "data/prices").glob("*.csv.gz")) + sorted((ROOT / "data/reference").glob("*.csv")):
        if path.is_file():
            input_manifest.append({"path": rel(path), "sha256": digest_bytes(path.read_bytes())})
    contract_file = ROOT / "scripts/prices/contracts.json"
    if contract_file.is_file():
        input_manifest.append({"path": rel(contract_file), "sha256": digest_bytes(contract_file.read_bytes())})
    address_map = {(normalize_chain(r["chain"]), norm(normalize_chain(r["chain"]), r["address_normalized"])): r for r in read_csv(ROOT / "data/addresses.csv")}
    ledger_map = defaultdict(list)
    for row in read_csv(ROOT / "data/ledger.csv"):
        for chain in row.get("chains", row["chain"]).split(";"):
            chain = normalize_chain(chain)
            ledger_map[(chain, norm(chain, row["address_normalized"]))].append(row)
    tornado = {key for key, items in ledger_map.items() if any("TORNADO CASH" in r["sdn_name"].upper() for r in items)}
    label_map = defaultdict(list)
    for row in read_csv(ROOT / "data/labels/labels.csv"):
        label_map[(row["chain"], row["address_normalized"])].append(row)
    paths = sorted(ROOT / p for p in manifest_paths) if manifest_paths is not None else sorted(
        p for p in (ROOT / "data/timelines").glob("*/*") if p.name.endswith((".json.gz", ".json")))
    statuses = {}
    rows = []
    wallet_tornado = []
    file_errors = []
    for file_index, path in enumerate(paths):
        file_start = len(rows)
        tornado_start = len(wallet_tornado)
        status_key = None
        try:
            filename_address = path.name[:-8] if path.name.endswith(".json.gz") else path.name[:-5]
            filename_chain = normalize_chain(path.parent.name)
            filename_key = (filename_chain, norm(filename_chain, filename_address))
            if filename_key not in address_map:
                # Same-string checks on other chains are outside this analysis.
                # Keep their inventory, not mutable irrelevant file contents.
                input_manifest.append({"path": rel(path), "sha256": None, "excluded": "nonledger chain-address filename"})
                diagnostics["nonledger_timeline_files_excluded"] += 1
                continue
            entry = {"path": rel(path), "sha256": digest_file(path)}
            input_manifest.append(entry)
            if path.stat().st_size > 25 * 1024 * 1024:
                print(f"Reading large timeline {file_index + 1}/{len(paths)}: {rel(path)}", file=sys.stderr, flush=True)
            retain = filename_key not in tornado
            timeline = load_compact_timeline(path, retain_events=retain)
            if not isinstance(timeline, dict) or not isinstance(timeline.get("txs"), list) or not isinstance(timeline.get("coverage"), dict):
                raise ValueError("missing timeline txs/coverage object")
            chain = normalize_chain(timeline["chain"])
            address = norm(chain, timeline["address"])
            key = (chain, address)
            if key != filename_key:
                raise ValueError("timeline identity differs from file chain/address")
            if key not in address_map:
                diagnostics["nonledger_timeline_files_excluded"] += 1
                continue
            if key in statuses:
                diagnostics["duplicate_address_timeline_files_skipped"] += 1
                continue
            a = address_map[key]
            start = date_boundary(a["first_listed_date"])
            end = date_boundary(a.get("delisted_date"))
            cov = timeline["coverage"]
            txs = timeline["txs"]
            tx_count = timeline["_observed_transactions"]
            reported = [cov.get("expected_confirmed_txs"), cov.get("reported_history_records"),
                        timeline.get("reported_history_records")]
            for value in (timeline.get("reported_transaction_counts") or {}).values() if isinstance(timeline.get("reported_transaction_counts"), dict) else []:
                if isinstance(value, (int, float)):
                    reported.append(value)
            exchange_scale = tx_count > 10000 or bool(cov.get("huge_address")) or any(isinstance(v, (int, float)) and v > 10000 for v in reported)
            statuses[key] = {"chain": chain, "address": address, "timeline_ref": rel(path),
              "complete": cov.get("complete") is True,
              "provider_complete": cov.get("complete") is True, "ledger_trackable": a["trackable"].lower() == "true", "exchange_scale": exchange_scale,
              "recipient_scope": "tornado_listed_cohort" if key in tornado or timeline.get("tornado_pool") else "non_tornado",
              "coverage_notes": cov.get("notes", []), "checked_through": cov.get("checked_through_time") or cov.get("to_time") or timeline.get("fetched_at"),
              "raw_ref": sorted(set(filter(None, [a.get("raw_ref", ""), cov.get("head_raw_ref", "")] + cov.get("raw_refs", [])))),
              "fetched_at": timeline.get("fetched_at"), "listed_date": a["first_listed_date"], "delisted_date": a.get("delisted_date", ""),
              "observed_transactions": number(tx_count, "transactions")}
            status_key = key
            # Deposit histories belong to the Tornado analysis; router and pool
            # receipts cannot be added together without double-counting funds.
            if statuses[key]["recipient_scope"] == "tornado_listed_cohort":
                diagnostics["tornado_timeline_files_reserved_for_tornado_job"] += 1
                continue
            if not start:
                diagnostics["timeline_missing_designation_date"] += 1
                continue
            real_counterparties = defaultdict(set)
            incoming_signatures = set()
            for event in txs:
                if not isinstance(event, dict) or event.get("direction") != "in":
                    continue
                timestamp = parse_time(event.get("time_utc"))
                if timestamp and timestamp >= start:
                    sources = [event["from"]] if event.get("from") else event.get("input_addresses", [])
                    incoming_signatures.update(signature(norm(chain, source)) for source in sources)
            seen_events = set()
            ordered = sorted(enumerate(txs), key=lambda pair: (str(pair[1].get("time_utc") or ""), pair[0]) if isinstance(pair[1], dict) else ("", pair[0]))
            for index, event in ordered:
                if not isinstance(event, dict):
                    diagnostics["malformed_events_skipped"] += 1
                    continue
                direction = event.get("direction")
                if direction not in ("in", "out"):
                    continue
                timestamp = parse_time(event.get("time_utc"))
                if timestamp is None:
                    diagnostics["events_without_exact_time_skipped"] += 1
                    continue
                if timestamp < start and (direction == "in" or not incoming_signatures):
                    continue
                if event.get("success") is False or event.get("is_transfer") is False:
                    diagnostics["failed_or_nontransfer_events_excluded"] += 1
                    continue
                try:
                    amount = Decimal(str(event["amount"]))
                    if not amount.is_finite() or amount < 0:
                        raise InvalidOperation
                except (KeyError, InvalidOperation):
                    diagnostics["invalid_amount_events_skipped"] += 1
                    continue
                identity, recognised = asset_identity(chain, event)
                price, valued_at, price_source, price_url, price_ref = quote(identity, event["time_utc"])
                usd_value = amount * price if price is not None else (Decimal(0) if amount == 0 and recognised else None)
                if direction == "out":
                    counterparties = [event["to"]] if event.get("to") else event.get("output_addresses", event.get("counterparties", []))
                    if recognised and usd_value is not None and usd_value >= 1:
                        for cp in counterparties:
                            cp = norm(chain, cp)
                            if cp and cp != address:
                                sig = signature(cp)
                                if sig in incoming_signatures:
                                    real_counterparties[sig].add(cp)
                                if (chain, cp) in tornado and timestamp >= start and key not in tornado:
                                    destination = address_map.get((chain, cp), {})
                                    delist = date_boundary(destination.get("delisted_date"))
                                    target_start = date_boundary(destination.get("first_listed_date"))
                                    if target_start and timestamp >= target_start:
                                        wallet_tornado.append({"chain": chain, "address": address, "tornado_address": cp,
                                          "period": "after_delisting" if delist and timestamp >= delist else "during_sanctions",
                                          "time_utc": event["time_utc"], "hash": event["hash"], "source_url": EXPLORERS.get(chain, "") + event["hash"],
                                          "asset": event["asset"], "amount": str(amount), "usd": str(usd_value), "valued_at": valued_at,
                                          "raw_ref": event.get("raw_ref", ""), "price_raw_ref": price_ref, "timeline_ref": rel(path),
                                          "sender_addresses": [address], "sender_basis": "listed_wallet_outgoing_event",
                                          "sender_class": "listed_wallet", "classification_rule": "recognised_real_outflow_to_tornado_listed_address",
                                          "amount_attribution": "full outgoing event; multi-output UTXO targets would require output attribution"})
                    continue
                if timestamp < start:
                    continue
                event_key = (event.get("hash"), event.get("event_id") or (event.get("kind"), event.get("traceId"), event.get("logIndex"), event.get("transfer_ordinal", 0), event.get("asset"), event.get("from"), event.get("to"), str(amount)))
                if event_key in seen_events:
                    diagnostics["duplicate_inflow_events_skipped"] += 1
                    continue
                seen_events.add(event_key)
                sender_list, sender_basis = senders(chain, event, address, diagnostics)
                mimics = sorted({cp for sender in sender_list for cp in real_counterparties.get(signature(sender), set()) if cp != sender})
                cls, rule, confidence = classify(amount, usd_value, recognised, bool(mimics))
                sender_class, sender_claims, sender_refs = label_sender(chain, sender_list, timestamp, a, address_map, label_map)
                raw_ref = event.get("raw_ref", "")
                if not raw_ref or not (ROOT / raw_ref.split("#", 1)[0]).is_file():
                    diagnostics["inflow_rows_with_missing_raw_evidence"] += 1
                names = sorted({r["sdn_name"] for r in ledger_map[key]})
                row = {"chain": chain, "address": address, "recipient_scope": statuses[key]["recipient_scope"],
                 "sdn_uids": sorted(set(a.get("sdn_uids", a.get("all_entity_uids", "")).split(";"))), "sdn_names": names,
                 "programs": sorted(filter(None, a["programs"].split(";"))), "listed_date": a["first_listed_date"],
                 "delisted_date": a.get("delisted_date", ""), "period": "after_delisting" if end and timestamp >= end else "during_sanctions",
                 "time_utc": event["time_utc"], "days_after_T": format((timestamp - start).total_seconds() / 86400, ".8f"),
                 "designation_day_ambiguous": timestamp.astimezone(ET).date().isoformat() == a["first_listed_date"][:10],
                 "hash": event.get("hash", ""), "event_id": event.get("event_id") or f"{event.get('hash')}:{event.get('kind', event.get('event_type', 'event'))}:{event.get('logIndex', event.get('traceId', index))}:{event.get('transfer_ordinal', 0)}",
                 "kind": event.get("kind", event.get("event_type", "transaction")), "asset": event.get("asset", ""),
                 "symbol": event.get("symbol") or "", "amount": str(amount),
                 "amount_convention": "positive_net_address_receipt; not gross outputs" if "input_value" in event else "asset_transfer_event",
                 "inflow_class": cls, "classification_status": "classified" if cls else "unresolved",
                 "classification_rule": rule, "classification_confidence": confidence, "mimicked_counterparty": mimics,
                 "usd": str(usd_value) if usd_value is not None else "", "valued_at": valued_at or "", "price_asset": identity or "",
                 "price_usd": str(price) if price is not None else "", "price_source": price_source or "",
                 "price_source_url": price_url, "price_raw_ref": price_ref, "sender_addresses": sender_list,
                 "sender_basis": sender_basis, "sender_class": sender_class, "sender_label_claims": sender_claims,
                 "sender_label_raw_refs": sender_refs, "timeline_complete": statuses[key]["complete"],
                 "exchange_scale": exchange_scale, "timeline_ref": rel(path), "raw_ref": raw_ref,
                 "source_url": EXPLORERS.get(chain, "") + event.get("hash", "")}
                rows.append(row)
        except (OSError, EOFError, zlib.error, json.JSONDecodeError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            del rows[file_start:]
            del wallet_tornado[tornado_start:]
            if status_key is not None:
                statuses.pop(status_key, None)
            diagnostics["unreadable_or_partial_timeline_files_skipped"] += 1
            file_errors.append({"path": rel(path), "error_type": type(exc).__name__, "reason": str(exc)[:180]})
        if (file_index + 1) % 250 == 0:
            print(f"Read {file_index + 1}/{len(paths)} timeline files; {len(statuses)} ledger addresses; {len(rows)} inflow rows", file=sys.stderr, flush=True)
    rows.sort(key=lambda r: (r["chain"], r["address"], r["time_utc"], r["hash"], r["event_id"]))
    wallet = [r for r in rows if r["recipient_scope"] == "non_tornado" and r["period"] == "during_sanctions"]
    real = [r for r in wallet if r["inflow_class"] == "real"]
    rankings = rank_addresses(wallet, statuses)
    coverage = []
    for chain in sorted({k[0] for k in address_map}):
        keys = [k for k in address_map if k[0] == chain]
        present = [k for k in keys if k in statuses]
        coverage.append({"chain": chain, "ledger_addresses": number(len(keys), "addresses"),
          "trackable_addresses": number(sum(address_map[k]["trackable"].lower() == "true" for k in keys), "addresses"),
          "untrackable_addresses": number(sum(address_map[k]["trackable"].lower() != "true" for k in keys), "addresses"),
          "addresses_with_timelines": number(len(present), "addresses"), "complete_history_addresses": number(sum(statuses[k]["complete"] for k in present), "addresses"),
          "missing_timelines": number(len(keys) - len(present), "addresses"),
          "raw_ref": sorted({address_map[k]["raw_ref"] for k in keys if address_map[k].get("raw_ref")})})
    decay = []
    for low, high in BOUNDS:
        items = [r for r in wallet if float(r["days_after_T"]) >= low and (high is None or float(r["days_after_T"]) < high)]
        eligible = eligible_complete = 0
        for key, s in statuses.items():
            if s["recipient_scope"] != "non_tornado":
                continue
            cutoff = parse_time(s["checked_through"])
            delist = date_boundary(s["delisted_date"])
            if cutoff and delist:
                cutoff = min(cutoff, delist)
            if cutoff and (cutoff - date_boundary(s["listed_date"])).total_seconds() / 86400 >= low:
                eligible += 1
                eligible_complete += s["complete"]
        decay.append({"from_day_inclusive": number(low, "days"), "to_day_exclusive": number(high, "days"),
          "addresses_old_enough_in_checked_data": number(eligible, "addresses"),
          "complete_history_addresses_old_enough": number(eligible_complete, "addresses"), **summary(items)})
    result = {"schema_version": "inflows-1", "provisional": True,
      "generated_at_utc": generated_at or dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
      "script": SCRIPT, "scope": "OFAC-listed chain-address pairs only; incoming asset events at/after T midnight ET; Tornado timeline presence counted but incoming events reserved for tornado job; wallet headline excludes post-delisting receipts",
      "timeline_count": number(len(statuses), "addresses"),
      "coverage": {"ledger_addresses": number(len(address_map), "addresses"), "addresses_with_timelines": number(len(statuses), "addresses"),
        "complete_history_addresses": number(sum(s["complete"] for s in statuses.values()), "addresses"),
        "untrackable_addresses": number(sum(a["trackable"].lower() != "true" for a in address_map.values()), "addresses"),
        "missing_timelines": number(len(address_map) - len(statuses), "addresses"), "by_chain": coverage,
        "file_errors": file_errors, "diagnostics": {k: number(v, "events" if "events" in k or "rows" in k or "lookup" in k else "files") for k, v in sorted(diagnostics.items())},
        "address_status": [statuses[k] for k in sorted(statuses)]},
      "rules": {"T": "first_listed_date midnight America/New_York; designation-day receipts flagged as intraday ambiguous",
        "real": ">=1 USD at transfer time; recognised native asset/contract; no poisoning rule",
        "dust": "<1 USD; zero on recognised asset is dust unless mimic demonstrated",
        "poisoning": "token outside explicit recognised list (low-confidence operational spam bucket), or zero/<1 USD sender matching both first and last 4 characters of prior real outgoing counterparty",
        "unclassified": "recognised positive amount without saved transfer-time price; excluded from real/dust totals rather than inventing a value",
        "recognised_tokens": TOKENS, "token_list_limit": "off-list is not independent proof of fake-token intent; legitimate off-list assets may be false positives",
        "wrapped_assets": "WETH valued using ETH proxy; WBTC and liquid-staking tokens remain unpriced unless separately configured",
        "sender_labels": "public label claims, not ownership proof; no historical validity assumed where dates absent; cex_hot sender is a withdrawal lead only",
        "sender_counts": "chain-address pairs; UTXO input addresses are possible funding sources, not people; no outgoing change addresses counted as senders",
        "exchange_scale": ">10,000 observed distinct transaction hashes or provider-reported history records; incomplete histories can hide scale",
        "steady_drips": ">=12 real events across >=6 UTC months, median <=100 USD, largest event <50% of total",
        "one_time_large_or_dominant": "largest event >=80% of observed real inflow value",
        "valuation": VALUE_TIME, "decay": "age bins are descriptive counts, not causal decay; cohorts, missing history and unequal exposure differ",
        "deduplication": "within recipient, hash plus event id or kind/trace/log/ordinal identity; no cross-address netting; transfer counts differ from transactions",
        "check": "recomputes exactly the saved timeline path set; verifies bytes of all manifested inputs; changed inputs fail, new files wait until refresh"},
      "wallet_during_sanctions": summary(wallet),
      "wallet_during_sanctions_excluding_exchange_scale": summary([r for r in wallet if not r["exchange_scale"]]),
      "wallet_excluding_senders_sharing_recipient_ofac_uid": summary([r for r in wallet if r["sender_class"] != "same_listed_entity"]),
      "wallet_complete_history_only": summary([r for r in wallet if r["timeline_complete"]]),
      "wallet_post_delisting": summary([r for r in rows if r["recipient_scope"] == "non_tornado" and r["period"] == "after_delisting"]),
      "all_observed_post_T": summary(rows),
      "by_chain": grouped(wallet, "chain"), "by_program_overlapping": grouped(wallet, "programs"),
      "by_sender_class": grouped(real, "sender_class"), "decay_curve": decay,
      "address_rankings": rankings,
      "two_year_plus_by_program_overlapping": grouped([r for r in wallet if float(r["days_after_T"]) >= 730], "programs"),
      "two_year_plus_by_chain": grouped([r for r in wallet if float(r["days_after_T"]) >= 730], "chain"),
      "tornado_wallet_side": {"scope": "wallet_to_tornado requires a direct outgoing event at a listed non-Tornado address; pool/router incoming histories and depositor counts belong to tornado job",
         "contract_inflow_analysis_owner": "scripts/analysis/tornado.py; results/tornado.json; docs/analysis/TORNADO.md",
         "listed_wallet_transfers_during_tornado_sanctions": number(sum(r["period"] == "during_sanctions" for r in wallet_tornado), "events"),
         "listed_wallet_usd_during_tornado_sanctions": number(round(sum(float(r["usd"]) for r in wallet_tornado if r["period"] == "during_sanctions"), 2), "usd"),
         "listed_wallet_transfers_after_tornado_delisting": number(sum(r["period"] == "after_delisting" for r in wallet_tornado), "events"),
         "listed_wallet_usd_after_tornado_delisting": number(round(sum(float(r["usd"]) for r in wallet_tornado if r["period"] == "after_delisting"), 2), "usd"),
         "examples_during": distinct_examples([r for r in wallet_tornado if r["period"] == "during_sanctions"]),
         "examples_after_delisting": distinct_examples([r for r in wallet_tornado if r["period"] == "after_delisting"]),
         "transfer_evidence": wallet_tornado},
      "headline_candidates": [], "input_manifest": sorted(input_manifest, key=lambda e: e["path"])}
    # Select three different kinds of case rather than three copies of a large exchange.
    picks = []
    if rankings:
        picks.append(("largest_observed_wallet_receipts", rankings[0]))
    late = [a for a in rankings if a["two_year_plus_real_events"]["value"] >= 2]
    if late:
        picks.append(("receipts_years_after_designation", max(late, key=lambda a: a["latest_age_days"]["value"])))
    drips = [a for a in rankings if a["pattern"] == "steady_drips"]
    if drips:
        picks.append(("steady_drips", max(drips, key=lambda a: a["active_months"]["value"])))
    one_sender = [a for a in rankings if a["real_events"]["value"] >= 8 and a["distinct_known_sender_addresses"]["value"] == 1]
    if one_sender:
        picks.append(("repeated_receipts_from_one_sender", max(one_sender, key=lambda a: a["real_inflow_usd"]["value"])))
    for candidate_id, item in picks:
        candidate_rows = [r for r in real if (r["chain"], r["address"]) == (item["chain"], item["address"])]
        class_breakdown = grouped(candidate_rows, "sender_class")
        shared = [r for r in candidate_rows if r["sender_class"] == "same_listed_entity"]
        result["headline_candidates"].append({"id": candidate_id, **item,
          "sender_class_breakdown": class_breakdown,
          "receipts_from_senders_sharing_recipient_ofac_uid": summary(shared),
          "example_evidence_checks": [audit_example(ex) for ex in (item["late_examples"] if candidate_id == "receipts_years_after_designation" else item["examples"])],
          "confidence": "High confidence in saved recognised-asset transfer arithmetic; provisional history and label coverage. Motive, beneficial ownership and number of people are not inferred. Positive net receipts on UTXO chains can include own-fund consolidation. Off-list tokens and unpriced recognised assets excluded.",
          "script": SCRIPT})
    filtered = [r for r in wallet if r["inflow_class"] in {"dust", "poisoning"}]
    mimic = [r for r in wallet if r["classification_rule"].startswith("zero_or_below_1_usd_sender_matches")]
    result["classification_audit"] = {
       "dust_or_operational_spam_share_of_incoming_records": number(round(len(filtered) / len(wallet), 8) if wallet else None, "share"),
       "zero_value_dust_records": number(sum(r["classification_rule"] == "zero_value_without_demonstrated_mimic" for r in wallet), "events"),
       "mimic_pattern_records": number(len(mimic), "events"),
       "mimic_examples": distinct_examples(mimic),
       "unpriced_recognised_asset_examples": [example(r) for r in wallet if not r["inflow_class"]],
       "confidence": "Recorded zero/low value is factual; a matching address pattern or missing token-list entry does not establish intent. These records are not all payments."}
    return result, rows


def csv_text(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return output.getvalue()


def v(obj, key):
    return obj[key]["value"]


def money(value):
    return f"${value:,.2f}"


def render_doc(result):
    cov = result["coverage"]
    s = result["wallet_during_sanctions"]
    lines = ["# Inflows after designation — provisional", "",
      f"Snapshot: **{result['generated_at_utc']}**. **{v(cov, 'addresses_with_timelines'):,} / {v(cov, 'ledger_addresses'):,} ledger chain-address pairs** have readable timelines; **{v(cov, 'complete_history_addresses'):,}** have provider-complete scoped histories. Ledger trackability is reported separately. {('Fetchers are still running.' if result.get('provisional', True) else 'Data as of ' + result['generated_at_utc'][:10] + '; bounded acquisition is complete and source-specific history gaps remain.')} These are observations within data checked, not whole-project totals.", "",
      f"Non-Tornado addresses received **{v(s, 'real_events'):,} real asset-transfer events**, worth **{money(v(s, 'real_inflow_usd'))} at transfer time** while listed. This is summed turnover, not unique money or customer payments. The records identify **{v(s, 'distinct_known_sender_addresses'):,} funding/sender addresses**, not people; **{v(s, 'real_events_without_identified_sender'):,}** real events have no identified direct sender.", "",
      f"Excluded from that real-event total: **{v(s, 'dust_events'):,} dust events**, **{v(s, 'poisoning_events'):,} operational poisoning/spam events**, and **{v(s, 'unclassified_price_events'):,} recognised-asset events without a price**. Off-list-token spam classification is low confidence and may exclude legitimate tokens.", "",
      "## Reproduce and refresh", "", "```sh", ".venv/bin/python -B scripts/analysis/inflows.py",
      ".venv/bin/python -B scripts/analysis/inflows.py --check", ".venv/bin/python -B scripts/analysis/inflows.py --self-test", "```", "",
      "The first command atomically replaces the analysis CSV, JSON and write-up. It works on whichever saved files exist. `--check` verifies input digests, recomputes the saved timeline path set and compares all three outputs. New files are ignored during that check; an overwritten ledger timeline or other relevant changed input causes an explicit failure and calls for refresh. Missing/truncated candidate ledger JSON or gzip files are counted and skipped; other-chain filenames are counted as outside scope. Machine-readable table rows carry `raw_ref` files and USD aggregates also carry price raw files; exact event pointers and request provenance are in the CSV and saved raw envelopes. No API calls, key reads, installs or shared-file writes occur.", "",
      "## Candidate findings", ""]
    for item in result["headline_candidates"]:
        lines += [f"### {item['id'].replace('_', ' ').capitalize()}", "",
          f"**{'; '.join(item['sdn_names'])}** — `{item['chain']}:{item['address']}` (listed {item['listed_date']}).",
          f"Observed **{v(item, 'real_events'):,} real events**, **{money(v(item, 'real_inflow_usd'))} at transfer time**, and **{v(item, 'distinct_known_sender_addresses'):,} distinct known funding/sender addresses**. {v(item, 'real_events_without_identified_sender'):,} events lack an identified sender. Latest receipt: {item['last_real_inflow']} (**{v(item, 'latest_age_days'):,.2f} days** after T).",
          f"Pattern: `{item['pattern']}`. Largest event **{money(v(item, 'largest_inflow_usd'))}**, **{v(item, 'largest_inflow_share'):.1%}** of observed value; **{v(item, 'active_months')} active months**, longest consecutive run **{v(item, 'longest_consecutive_months')} months**; median event **{money(v(item, 'median_inflow_usd'))}**. Amounts use each transfer's historical observation, not current prices.",
          f"Two years or more after T: **{v(item, 'two_year_plus_real_events'):,} real events**, **{money(v(item, 'two_year_plus_usd'))} at those transfer times**.",
          f"Confidence: {item['confidence']} Timeline complete flag: `{item['timeline_complete']}`; exchange-scale flag: `{item['exchange_scale']}`.", ""]
        shared = item["receipts_from_senders_sharing_recipient_ofac_uid"]
        if v(shared, "real_events"):
            lines += [f"**Attribution caveat:** **{v(shared, 'real_events')} events / {money(v(shared, 'real_inflow_usd'))} at transfer time** came from addresses sharing the recipient's OFAC UID. These are transfers between addresses listed under the same name, not evidence of outside payments.", ""]
        examples = item["late_examples"] if item["id"] == "receipts_years_after_designation" else item["examples"]
        for ex in examples:
            lines.append(f"- [{ex['hash']}]({ex['source_url']}) — {ex['time_utc']}; {ex['amount']} {ex['asset']}; {money(float(ex['usd']))}, price observed {ex['valued_at']}; raw `{ex['raw_ref']}`; price raw `{ex['price_raw_ref']}`.")
        lines += ["", "Raw example checks: " + "; ".join(f"`{check['hash']}`: {check['status']}" for check in item["example_evidence_checks"]) + "."]
        lines += [""]
    lines += ["## Scope and sensitivity", "",
      f"Without exchange-scale addresses: **{v(result['wallet_during_sanctions_excluding_exchange_scale'], 'real_events'):,} real events**, **{money(v(result['wallet_during_sanctions_excluding_exchange_scale'], 'real_inflow_usd'))} at transfer time**. Scale is >10,000 observed distinct transaction hashes or provider-reported history; incomplete histories may conceal scale.",
      f"Complete-history timelines only: **{v(result['wallet_complete_history_only'], 'real_events'):,} real events**, **{money(v(result['wallet_complete_history_only'], 'real_inflow_usd'))} at transfer time**.",
      f"Excluding senders that share the recipient's OFAC UID leaves **{v(result['wallet_excluding_senders_sharing_recipient_ofac_uid'], 'real_events'):,} real events / {money(v(result['wallet_excluding_senders_sharing_recipient_ofac_uid'], 'real_inflow_usd'))} at transfer time**. The remainder is not necessarily external customer funding; unlabelled addresses can also be related.",
      f"Designation-date sensitivity: **{v(s, 'real_events_on_designation_date'):,} real events** fall on T's ET calendar date, whose intraday publication time is unknown. Excluding that entire day leaves **{money(v(s, 'real_usd_after_designation_day'))} at transfer time**.", "",
      "An event is an asset transfer, not a transaction. Several events can share one transaction hash. UTXO histories supply positive net address receipts rather than gross output receipts; change and self-funding cannot be inferred away. Incoming sender counts use input addresses only, never other outputs. Tornado's entire listed address cohort is separated conservatively, including role-unresolved administrative addresses. Same-string activity on non-listed EVM chains is excluded.", "",
      "## Chain coverage", "", "| Chain | Ledger addresses | Timeline addresses | Complete history | Untrackable |", "|---|---:|---:|---:|---:|"]
    for row in cov["by_chain"]:
        lines.append(f"| {row['chain']} | {v(row, 'ledger_addresses')} | {v(row, 'addresses_with_timelines')} | {v(row, 'complete_history_addresses')} | {v(row, 'untrackable_addresses')} |")
    lines += ["", "Per-chain status, source notes, missing files and explicit skip counts (including zero) are under `coverage` in `results/inflows.json`. Additional source-specific limits are linked from `docs/COVERAGE.md`. `docs/sources/UTXO.md` reports a working BTG history despite the earlier ledger's untrackable flag; both fields are preserved, with provider completeness controlling coverage. Native-UTXO completeness does not cover Omni, CashTokens/SLP or shielded flows. Missing ZEC/XVG routes and Monero privacy limits do not establish inactivity. `docs/sources/TRON.md` distinguishes exhausted paging from balance reconciliation and notes unresolved multiplicity for identical TRC-20 logs without log indexes. A complete history flag here is not independent financial reconciliation; these are observed events, with that source limitation retained.", "",
      "## Programs and receipts years later", "", "Program memberships overlap: do not sum program rows. These are native receipts; no donation, ransomware-payment or payroll motive is established from a transfer alone.", "",
      "| Program | Real events while listed | USD at transfer time | Receiving addresses | Real events ≥2 years later |", "|---|---:|---:|---:|---:|"]
    late_programs = {r["programs"]: r for r in result["two_year_plus_by_program_overlapping"]}
    for row in sorted(result["by_program_overlapping"], key=lambda r: v(r, "real_inflow_usd"), reverse=True):
        late = v(late_programs[row["programs"]], "real_events") if row["programs"] in late_programs else 0
        lines.append(f"| {row['programs']} | {v(row, 'real_events'):,} | {money(v(row, 'real_inflow_usd'))} | {v(row, 'receiving_addresses')} | {late:,} |")
    lines += ["", "### Targeted leads: Tron SDGT, DPRK and named ransomware cases", ""]
    relevant = [a for a in result["address_rankings"] if (a["chain"] == "TRX" and "SDGT" in a["programs"]) or any("DPRK" in p for p in a["programs"]) or any(any(term in name.upper() for term in ("SUEX", "CHATEX", "HYDRA", "LOCKBIT", "EVIL", "CRYPTOLOCKER", "KHORASHADIZADEH", "GHORBANIYAN", "HIKMAT")) for name in a["sdn_names"])]
    for item in sorted(relevant, key=lambda a: (v(a, "two_year_plus_real_events") > 0, v(a, "real_inflow_usd")), reverse=True)[:12]:
        lines.append(f"- {'; '.join(item['sdn_names'])}, `{item['chain']}:{item['address']}`: **{v(item, 'real_events'):,} real events / {money(v(item, 'real_inflow_usd'))} at transfer time**; **{v(item, 'two_year_plus_real_events'):,}** events ≥2 years after listing; latest {item['last_real_inflow']}; {item['pattern']}; timeline complete `{item['timeline_complete']}`. Example: [{item['examples'][0]['hash']}]({item['examples'][0]['source_url']}). Full evidence is in `address_rankings`.")
    if not relevant:
        lines.append("No priced real receipts in the requested case cohorts have been found in this snapshot; missing history is not evidence of no payments.")
    lines += ["", "## Sender label classes", "", "| Sender class | Real events | USD at transfer time |", "|---|---:|---:|"]
    for row in sorted(result["by_sender_class"], key=lambda r: v(r, "real_inflow_usd"), reverse=True):
        lines.append(f"| {row['sender_class']} | {v(row, 'real_events'):,} | {money(v(row, 'real_inflow_usd'))} |")
    lines += ["", "A labelled hot-wallet sender is a CEX withdrawal lead. It does not identify the customer or establish legal responsibility. Deposit-labelled senders retain their separate role; conflicting labels stay ambiguous. Other-sanctioned classification uses designation/delisting dates at transfer time. Shared OFAC UIDs are marked `same_listed_entity`. Undated public service labels may not have been valid historically. Missing labels mean unlabelled, not private persons.", "",
      "## Timing curve", "", "| Days after T (inclusive / exclusive) | Real events | USD at transfer time | Addresses old enough in checked data |", "|---|---:|---:|---:|"]
    for row in result["decay_curve"]:
        lines.append(f"| {v(row, 'from_day_inclusive')}–{v(row, 'to_day_exclusive') if v(row, 'to_day_exclusive') is not None else 'latest'} | {v(row, 'real_events'):,} | {money(v(row, 'real_inflow_usd'))} | {v(row, 'addresses_old_enough_in_checked_data')} |")
    lines += ["", "These age bins are a descriptive timing curve. Different designation cohorts, incomplete acquisition, unequal bin widths and unequal time exposed prevent interpreting the raw decline as a sanctions effect. Complete-history eligibility counts are retained in JSON.", "",
      "## Tornado analysis: wallet side", ""]
    tc = result["tornado_wallet_side"]
    lines += [f"- Direct transfers from other listed addresses to the Tornado cohort: **{v(tc, 'listed_wallet_transfers_during_tornado_sanctions'):,} events / {money(v(tc, 'listed_wallet_usd_during_tornado_sanctions'))}** during Tornado sanctions; **{v(tc, 'listed_wallet_transfers_after_tornado_delisting'):,} events / {money(v(tc, 'listed_wallet_usd_after_tornado_delisting'))}** after Tornado delisting. All USD is valued at each transfer time.",
      "", "The Tornado analysis covers contract-specific deposit analysis, matched-window comparisons and delisting interpretation (`results/tornado.json`, `docs/analysis/TORNADO.md`). This output includes `tornado_wallet_side.transfer_evidence`. Tornado timelines are read to count availability, but their incoming events are covered by that separate analysis. Pool logs without sender information cannot establish unique wallet depositors. Summing router and pool receipts would double-count routed funds.", ""]
    for field in ("examples_during", "examples_after_delisting"):
        for ex in tc[field]:
            lines.append(f"- {field}: [{ex['hash']}]({ex['source_url']}) — {ex['time_utc']}; {money(float(ex['usd']))}, price observed {ex['valued_at']}; raw `{ex['raw_ref']}`.")
    audit = result["classification_audit"]
    lines += ["", "## Why the filter matters", "",
      f"**{v(audit, 'dust_or_operational_spam_share_of_incoming_records'):.2%} of observed during-sanctions incoming records** are dust or operational spam under these rules; **{v(audit, 'zero_value_dust_records'):,}** are zero-value records without a demonstrated mimic. This share is about records, not people or transferred value. **{v(audit, 'mimic_pattern_records')}** records meet the prior-counterparty address-mimic rule. Confidence: {audit['confidence']}", ""]
    for ex in audit["mimic_examples"]:
        lines.append(f"- Mimic-rule example: [{ex['hash']}]({ex['source_url']}) — {ex['time_utc']}; {ex['amount']} {ex['asset']}; raw `{ex['raw_ref']}`. Exact matching counterparty is recorded in the CSV.")
    for ex in audit["unpriced_recognised_asset_examples"]:
        lines.append(f"- **Unpriced and excluded from real/dust totals:** {ex['amount']} {ex['asset']} to `{ex['address']}` on {ex['time_utc']}; [{ex['hash']}]({ex['source_url']}); raw `{ex['raw_ref']}`. This can be economically material; no USD is invented.")
    lines += ["", "## Classification, valuation and limits", "",
      "Every usable post-T incoming row carries its rule in `data/derived/inflows.csv`. Native asset/recognised contract receipts ≥$1 are real; <$1 are dust. A sender matching both the first and last four characters of a different, prior real outgoing counterparty is marked poisoning only for zero/<$1 receipts. Zero without a demonstrated mimic stays dust. Tokens outside the explicit list in the script/JSON enter the poisoning/spam bucket with low confidence; this is an operational token-list rule, not proof of intent. The rule is deliberately visible so a broader reviewed token list can change the classification.",
      "Positive recognised-asset events without a saved price remain unresolved with an empty `inflow_class`. This is an explicit exception proposed to the three-class requirement: fabricating a USD threshold would violate the price/evidence rules. `unclassified_price_events` counts them; no unavailable price is replaced with zero or $1. Stablecoins use saved historical quotes. WETH uses an explicit ETH price proxy; WBTC and other assets without a configured price are not silently valued as their underlying.",
      "USD figures are the sum of per-event valuations using `scripts/prices/price.py usd()`: latest saved hourly observation at/before the transfer if at most two hours old, otherwise daily at most two days old. Each row records the actual observation time, quote, source URL and raw response. Figures are estimates at the available observation frequency, not exact executable prices. Addresses, asset events, transactions, programs and people remain different units.",
      "No inference identifies the controller of an unlabelled address or a sender's motive. Receiving funds does not establish a legal violation. Research, not legal or compliance advice.", "",
      "Prior-art distinction: this listed-address-only, evidence-linked cross-chain analysis separates dust/spam, net UTXO receipts, sender-label uncertainty and persistent post-designation receipts. It does not reproduce vendor exchange clusters or assume this partial sample equals vendor totals. See `data/reference/vendor_claims.csv` and `docs/PRIOR_ART.md` for the claims and scope limits.", ""]
    return "\n".join(lines)


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def self_test():
    assert date_boundary("2022-08-08").isoformat() == "2022-08-08T04:00:00+00:00"
    assert date_boundary("2022-12-08").isoformat() == "2022-12-08T05:00:00+00:00"
    assert classify(Decimal(1), Decimal("0.999999"), True, False)[0] == "dust"
    assert classify(Decimal(1), Decimal(1), True, False)[0] == "real"
    assert classify(Decimal(0), Decimal(0), True, False)[0] == "dust"
    assert classify(Decimal(0), Decimal(0), True, True)[0] == "poisoning"
    assert classify(Decimal(1), None, True, False)[0] == ""
    assert classify(Decimal(1000000), None, False, False)[0] == "poisoning"
    assert asset_identity("ETH", {"asset": "0x1234", "symbol": "USDT"}) == (None, False)
    assert asset_identity("ARB", {"asset": "ETH"}) == ("ETH", True)
    assert signature("0x1234aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa5678") == ("1234", "5678")
    assert streak({"2022-11", "2022-12", "2023-01", "2023-03"}) == 3
    a = {"first_listed_date": "2024-01-01", "delisted_date": "2025-01-01", "sdn_uids": "1", "raw_ref": "raw"}
    cls, _, _ = label_sender("ETH", ["sender"], parse_time("2023-01-01Z"), a, {("ETH", "sender"): a}, {})
    assert cls == "unlabelled"
    with tempfile.TemporaryDirectory(prefix="inflows-self-test-") as directory:
        fixture = Path(directory) / "timeline.json.gz"
        payload = {"txs": [{"hash": "h" * 1100000, "inputs": [{"omit": True}], "amount": "1"}], "coverage": {"complete": False}}
        fixture.write_bytes(gzip.compress(json.dumps(payload).encode()))
        loaded = load_compact_timeline(fixture)
        assert len(loaded["txs"][0]["hash"]) == 1100000 and "inputs" not in loaded["txs"][0]
        assert load_compact_timeline(fixture, retain_events=False)["_observed_transactions"] == 1
        for malformed in (b'{"txs":[{},]}', b'{"txs":[],}', b'{"txs":[]', b'{"txs":[]}garbage'):
            fixture.write_bytes(gzip.compress(malformed))
            try:
                load_compact_timeline(fixture)
            except (ValueError, EOFError):
                pass
            else:
                raise AssertionError("accepted malformed JSON")
        fixture.write_bytes(gzip.compress(b'{"txs":[]}')[:-4])
        try:
            load_compact_timeline(fixture)
        except (OSError, EOFError, zlib.error):
            pass
        else:
            raise AssertionError("accepted truncated gzip")
    print("PASS: classification thresholds, missing-price handling, token-symbol spoofing, ET boundaries, historical sender designation, bounded-memory JSON parsing and corrupt/partial input rejection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    previous = None
    if args.check:
        if not OUTPUT_JSON.is_file():
            print("FAIL: run inflows.py first", file=sys.stderr)
            return 1
        previous = json.loads(OUTPUT_JSON.read_text())
        changed = []
        for item in previous["input_manifest"]:
            if item.get("excluded"):
                continue
            path = ROOT / item["path"]
            if not path.is_file() or digest_file(path) != item["sha256"]:
                changed.append(item["path"])
        if changed:
            print("FAIL: saved inputs changed; refresh before --check:\n" + "\n".join(changed[:20]), file=sys.stderr)
            return 1
    paths = [i["path"] for i in previous["input_manifest"] if i["path"].startswith("data/timelines/")] if previous else None
    result, rows = build(paths, previous["generated_at_utc"] if previous else None)
    from scripts.lib.fetch_status import apply_status, report_status
    result = apply_status(result, ROOT, "inflows")
    outputs = {OUTPUT_JSON: json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
               OUTPUT_CSV: csv_text(rows), OUTPUT_DOC: report_status(render_doc(result), result)}
    if args.check:
        differences = [rel(path) for path, expected in outputs.items() if not path.is_file() or path.read_text(encoding="utf-8") != expected]
        if differences:
            print("FAIL: recomputed output differs: " + ", ".join(differences), file=sys.stderr)
            return 1
        print(f"PASS: three outputs reproduced from {len(paths)} saved timeline files; new files ignored")
    else:
        for path, text in outputs.items():
            atomic_write(path, text)
        print(json.dumps({"provisional": result["provisional"], "timeline_addresses": result["timeline_count"],
                          "csv_rows": number(len(rows), "events"),
                          "wallet": {k: v for k, v in result["wallet_during_sanctions"].items() if k not in {"raw_ref", "price_raw_ref"}}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
