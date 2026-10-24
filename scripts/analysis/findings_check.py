#!/usr/bin/env python3
"""Offline checks for JSON tags, independent freeze-audit tags, and tx examples.

Run with .venv/bin/python -I -S scripts/analysis/findings_check.py --check.
This checks the editorial layer, not a replacement for each producer's --check.
No project imports, network requests, credential reads, or output-file writes.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import gzip
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
TAG = re.compile(r"<!-- check: (results/[\w/-]+\.json)#(.+?) = (.+?) -->")
AUDIT_TAG = re.compile(r"<!-- audit-check: (data/verify/freeze_verify\.csv)#([a-z_]+) = (.+?) -->")
TX = re.compile(r"\[((?:0x)?[0-9a-fA-F]{64})\]\((https://[^\s)]+)\)")
RAW = re.compile(r"\braw `([^`]+)`")
NUMBER = re.compile(r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*%?")
HASH_KEYS = {"hash", "txid", "transactionhash", "transaction_id", "transaction_hash", "tx_id"}


def reject_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def decode(text):
    return json.loads(text, parse_float=Decimal, parse_constant=reject_constant)


def resolve(value, path):
    if path.startswith("/"):
        parts = [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:]]
    else:
        parts = [p for p in re.split(r"\.|\[|\]", path) if p]
    for part in parts:
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def confined(relative, directory):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to((ROOT / directory).resolve()):
        raise ValueError(f"Reference outside {directory}: {relative}")
    return path


def numbers(line):
    # Hashes, paths, dates and timestamps are identifiers/metadata, not quantities.
    line = re.sub(r"`[^`]*`|\[[^\]]*\]\([^)]*\)", "", line)
    line = re.sub(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z)?\b", "", line)
    return [m.group().strip().replace(",", "").replace("−", "-") for m in NUMBER.finditer(line)]


def display_matches(line, value, unit):
    for token in numbers(line):
        percent = token.endswith("%")
        literal = token.rstrip("%").strip()
        expected = Decimal(value) * (100 if percent and unit == "share" else 1)
        candidate = Decimal(literal)
        if "." in literal:
            expected = expected.quantize(Decimal(1).scaleb(candidate.as_tuple().exponent), rounding=ROUND_HALF_UP)
        if expected == candidate:
            return True
    return False


def contains_hash(value, tx_hash):
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in HASH_KEYS and isinstance(child, str) and child.lower() == tx_hash.lower():
                    return True
                if isinstance(child, (dict, list)):
                    pending.append(child)
        elif isinstance(item, list):
            pending.extend(item)
    return False


def movement_reconciliation(sources):
    """Compare address sets; pre-week movement and issuer timing are different facts."""
    checkpoints = sources['results/checkpoints.json']
    premove = sources['results/premove.json']
    key = lambda row: (row['chain'].upper(), row['address'])
    before = {key(row) for row in checkpoints['addresses'] if row['moved_before'] is True}
    wallets = {key(row) for row in checkpoints['addresses'] if row['moved_before'] is True
               and row['trackable'] and not row['tornado_excluded']}
    primary = [row for row in premove['address_results']
               if row['shift_days'] == 0 and row['window_days'] == 7]
    # any_outflow is a {value, unit} object: the dictionary itself is truthy
    # even when its value is zero.
    eligible_active = {key(row) for row in primary if row['real']['any_outflow']['value'] == 1}
    with (ROOT / 'data/derived/freeze_match.csv').open(newline='') as handle:
        freezes = {key(row) for row in csv.DictReader(handle)
                   if row['chain'] == 'TRX' and row['issuer'] == 'tether'
                   and row['lag_upper_hours'] and Decimal(row['lag_upper_hours']) < 0}
    headline = premove['candidate_findings'][0]
    expected = [checkpoints['aggregates']['overall'][0]['moved_before_addresses']['value'],
                checkpoints['headline_population']['moved_before_addresses']['value'],
                headline['denominator']['value'], headline['number']['value'],
                sources['results/freeze_match.json']['summary'][112]['definitely_before_publication']['value']]
    observed = [len(before), len(wallets), len(primary), len(eligible_active), len(freezes)]
    if observed != expected or not eligible_active.issubset(wallets):
        raise ValueError(f'Movement-set reconciliation failed: observed={observed}, expected={expected}')
    return {'checkpoint_preweek_all_listed_addresses': len(before),
            'checkpoint_preweek_non_tornado_addresses': len(wallets),
            'premove_primary_eligible_addresses': len(primary),
            'premove_primary_active_addresses': len(eligible_active),
            'tron_frozen_before_listing_day_addresses': len(freezes),
            'movement_and_early_freeze_intersection_addresses': len(before & freezes),
            'movement_only_addresses': len(before - freezes),
            'early_freeze_only_addresses': len(freezes - before),
            'negative_first_post_listing_noon_proxy_lags': sum(
                isinstance(row.get('first_outflow_lag_days'), (int, Decimal))
                and row['first_outflow_lag_days'] < 0 for row in checkpoints['addresses']),
            'interpretation': 'moved_before is a pre-listing-week flag; first_outflow_lag_days selects a post-listing outflow. Equal movement/freeze counts do not identify the same address set.'}


def independent_freeze_metrics():
    """Preserve the verifier's original cohort; do not use the later expansion."""
    with (ROOT / 'data/verify/freeze_verify.csv').open(newline='') as handle:
        cohort = [row for row in csv.DictReader(handle) if row['chain'] == 'TRX']
    known = [row for row in cohort if row['claimed_known_balance_cohort'].lower() == 'true']
    if any(not row['freeze_balance_usdt'] for row in known):
        raise ValueError('Independent claimed-known cohort contains an unknown freeze balance')
    return {'known_subtotal_native': {'value': sum((Decimal(row['freeze_balance_usdt']) for row in known), Decimal(0)), 'unit': 'native:USDT'},
            'known_addresses': {'value': len(known), 'unit': 'addresses'},
            'cohort_addresses': {'value': len(cohort), 'unit': 'addresses'},
            'unknown_addresses': {'value': len(cohort) - len(known), 'unit': 'addresses'}}


def check(path):
    # Load every result in full; do not import or execute any producer.
    sources = {}
    source_bytes = {}
    for result in sorted((ROOT / "results").glob("*.json")):
        content = result.read_bytes()
        sources[str(result.relative_to(ROOT))] = decode(content)
        source_bytes[result] = content
    lines = path.read_text().splitlines()
    checked = 0
    audit_checked = 0
    audit_metrics = independent_freeze_metrics()
    raw_cache = {}
    examples = 0
    finding_count = 0
    in_finding = False
    finding_examples = 0
    previous_prose = ""
    numerical_lines = {}
    tagged_lines = set()
    section = "preamble"
    errors = []

    for index, line in enumerate(lines):
        try:
            if line.startswith("## "):
                if in_finding and not 2 <= finding_examples <= 3:
                    raise ValueError(f"{section}: expected two or three transaction examples, got {finding_examples}")
                section = line[3:]
                in_finding = section != "What we could not see"
                finding_examples = 0
                if in_finding:
                    finding_count += 1
            result_match = TAG.fullmatch(line)
            audit_match = AUDIT_TAG.fullmatch(line)
            match = result_match or audit_match
            if ("<!-- check:" in line or "<!-- audit-check:" in line) and not match:
                raise ValueError("Tag must occupy its own line and include an explicit JSON value")
            if match:
                filename, dotted, literal = match.groups()
                if result_match:
                    confined(filename, "results")
                    actual = resolve(sources[filename], dotted)
                    parent = resolve(sources[filename], dotted.rsplit(".", 1)[0]) if "." in dotted else {}
                else:
                    confined(filename, 'data/verify')
                    parent = audit_metrics[dotted]
                    actual = parent['value']
                    audit_checked += 1
                expected = decode(literal)
                if isinstance(actual, bool) or not isinstance(actual, (int, Decimal)) or isinstance(expected, bool) or not isinstance(expected, (int, Decimal)):
                    raise ValueError("Tag target must be a numeric scalar")
                if actual != expected:
                    raise ValueError(f"Source changed: {filename}#{dotted} is {actual}, tag says {expected}")
                unit = parent.get("unit") if isinstance(parent, dict) else None
                if not display_matches(previous_prose, actual, unit):
                    raise ValueError(f"Rendered quantity does not match tag: {previous_prose}")
                tagged_lines.add(previous_index)
                checked += 1
                continue
            if line.strip() and not line.startswith("<!--"):
                previous_prose, previous_index = line, index
                if numbers(line):
                    numerical_lines[index] = line
            for tx in TX.finditer(line):
                if not in_finding:
                    continue
                raw_match = RAW.search(line)
                if not raw_match:
                    raise ValueError("Transaction example is missing its raw reference")
                tx_hash, explorer = tx.groups()
                if not explorer.lower().endswith(tx_hash.lower()):
                    raise ValueError("Explorer URL does not identify the displayed hash")
                reference = raw_match.group(1)
                filename, _, pointer = reference.partition("#")
                raw_path = confined(filename, "data/raw")
                if filename not in raw_cache:
                    opener = gzip.open if filename.endswith(".gz") else open
                    with opener(raw_path, "rt") as handle:
                        raw_cache[filename] = decode(handle.read())
                envelope = raw_cache[filename]
                if not isinstance(envelope, dict) or not envelope.get("request"):
                    raise ValueError("Saved response has no request metadata")
                response = resolve(envelope, pointer) if pointer else envelope.get("response", envelope)
                if not contains_hash(response, tx_hash):
                    raise ValueError(f"Transaction hash absent at raw reference: {reference}")
                finding_examples += 1
                examples += 1
        except (KeyError, IndexError, TypeError, ValueError, OSError, EOFError) as exc:
            errors.append(f"{path.name}:{index + 1}: {exc}")

    for index, line in numerical_lines.items():
        if index not in tagged_lines:
            errors.append(f"{path.name}:{index + 1}: untagged numerical line: {line}")
    if not 10 <= finding_count <= 15:
        errors.append(f"Expected ten to fifteen findings, got {finding_count}")
    for source, before in source_bytes.items():
        if source.read_bytes() != before:
            errors.append(f"Concurrent update during check: {source.relative_to(ROOT)}; retry after refresh")
    if errors:
        raise ValueError("\n".join(errors))
    return {"status": "PASS", "results_loaded": len(sources), "findings": finding_count,
            "numeric_tags": checked, "raw_transaction_examples": examples,
            "result_json_tags": checked - audit_checked, "independent_audit_tags": audit_checked,
            "distinct_raw_files_opened": len(raw_cache),
            "provisional_flags": {name: data.get('provisional') for name, data in sources.items()},
            "movement_reconciliation": movement_reconciliation(sources),
            "scope": "exact JSON and independent-audit tags, displayed rounding, quantity-line coverage, raw pointers/hashes/request metadata, and movement-set reconciliation; producer arithmetic requires producer --check"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check saved findings without writing files (the default).")
    parser.add_argument("--findings", type=Path, default=ROOT / "FINDINGS.md")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.findings), indent=2))
    except (ValueError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
