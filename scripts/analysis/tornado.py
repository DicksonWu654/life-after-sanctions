#!/usr/bin/env python3
"""Tornado Cash legal-event study. Stdlib only; writes only this analysis's owned paths.

Default: snapshot readable live inputs and rebuild provisional outputs, offline.
--fetch: additionally fill missing ETH pool logs, ambiguous UTC dates, selected
transaction origins, independent legal-date balances, and TORN market prices.
--check: reproduce JSON/CSV from the pinned input snapshot (no network), even
while the shared fetchers replace their timelines. --self-test checks semantics.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.prices.price import usd, _lookup_rows, parse_time

RAW = ROOT / "data/raw/tornado"
OUT = ROOT / "results/tornado.json"
DAILY = ROOT / "data/derived/tornado_daily.csv"
DOC = ROOT / "docs/analysis/TORNADO.md"
SNAPSHOT = RAW / "analysis_inputs.json.gz"
UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
RPC = "https://rpc.mevblocker.io"
DEPOSIT = "0xa945e51eec50ab98c161376f0db4cf2aeba3ec92755fe2fcd388bdbbb80ff196"
TORN = "0x77777feddddffc19ff86db637967013e6c6a116c"
EXPLORERS = {"eth": "https://etherscan.io", "arb": "https://arbiscan.io", "bsc": "https://bscscan.com", "polygon": "https://polygonscan.com", "op": "https://optimistic.etherscan.io"}
NATIVE = {"eth": "ETH", "arb": "ETH", "bsc": "BNB", "polygon": "POL", "op": "ETH"}
TOKENS = {"0x6b175474e89094c44da98b954eedeac495271d0f": "DAI", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC", "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT", "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC", "0x5d3a536e4d6dbd6114cc1ead35777bab948e3643": "cDAI", "0x39aa39c021dfbae8fac545936693ac917d5e7563": "cUSDC"}
LEGAL = [
    ("designation", "2022-08-08", "Initial OFAC designation", "https://ofac.treasury.gov/recent-actions/20220808"),
    ("redesignation", "2022-11-08", "Withdrawal and immediate re-designation", "https://ofac.treasury.gov/recent-actions/20221108"),
    ("van_loon", "2024-11-26", "Van Loon Fifth Circuit ruling", "https://www.ca5.uscourts.gov/opinions/pub/23/23-50669-CV0.pdf"),
    ("delisting", "2025-03-21", "OFAC removal", "https://ofac.treasury.gov/recent-actions/20250321"),
]


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def num(value):
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)


def rel(path):
    return str(Path(path).relative_to(ROOT))


def read_gz(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def write_gz(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.GzipFile(filename=str(tmp), mode="wb", mtime=0) as f:
        f.write(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())
    tmp.replace(path)


def metric(value, unit, valued_at=None):
    result = {"value": value, "unit": unit}
    if valued_at is not None:
        result["valued_at"] = valued_at
    return result


class EvidenceClient:
    """Keyless, bounded, resumable requests; errors remain saved evidence."""
    def __init__(self, budget=700):
        self.budget = budget
        self.calls = 0
        self.last = 0.0
        self.failures = []

    def request(self, url, body=None, attempts=3):
        if "etherscan" in urllib.parse.urlsplit(url).netloc:
            raise ValueError("This analysis never calls Etherscan")
        identity = {"url": url, "method": "POST" if body is not None else "GET", "body": body}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:28]
        path = RAW / "requests" / (digest + ".json.gz")
        if path.exists():
            cached = read_gz(path)
            return cached["response"], rel(path)
        for attempt in range(attempts):
            if self.calls >= self.budget:
                raise RuntimeError("Tornado request budget exhausted; rerun --fetch to resume")
            if self.calls % 100 == 0:
                size = sum(p.stat().st_size for p in (ROOT / "data").rglob("*") if p.is_file())
                if size > 8_700_000_000:
                    raise RuntimeError("Shared data approaches 10 GB cap; stopping acquisition")
            delay = .3 - (time.monotonic() - self.last)
            if delay > 0:
                time.sleep(delay)
            self.calls += 1
            self.last = time.monotonic()
            req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"User-Agent": "LifeAfterSanctions/1.0 public-chain-research", "Accept": "application/json", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=35) as r:
                    status, content = r.status, r.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                status, content = e.code, e.read().decode("utf-8", "replace")
            except (OSError, TimeoutError) as e:
                status, content = 0, type(e).__name__ + ": " + str(e)
            try:
                response = json.loads(content)
            except ValueError:
                response = {"non_json_body": content}
            error = status != 200 or isinstance(response, dict) and bool(response.get("error")) or isinstance(response, list) and any("error" in x for x in response)
            saved = {"request": identity, "fetched_at_utc": iso(dt.datetime.now(UTC)), "http_status": status, "response": response}
            target = path if not error else path.with_name(digest + f".error-{time.time_ns()}.json.gz")
            write_gz(target, saved)
            if not error:
                return response, rel(target)
            detail = str(response)[:300]
            self.failures.append({"raw_ref": rel(target), "reason": detail, "status": status})
            # Size errors need range splitting, not repeated unchanged requests.
            if any(w in detail.lower() for w in ("too many results", "response size", "block range", "limit exceeded")):
                break
            if attempt + 1 < attempts:
                time.sleep(min(10, 2 ** (attempt + 1)))
        raise RuntimeError(f"Source request failed ({status}): {detail}; {rel(target)}")

    def rpc(self, method, params, endpoint=RPC):
        result, ref = self.request(endpoint, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if not isinstance(result, dict) or result.get("result") is None:
            raise RuntimeError("Missing RPC result: " + ref)
        return result["result"], ref

    def batch(self, calls, endpoint=RPC, width=40):
        results = []
        for start in range(0, len(calls), width):
            group = calls[start:start + width]
            response, ref = self.request(endpoint, [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(group)])
            if not isinstance(response, list):
                raise RuntimeError("Expected RPC batch array: " + ref)
            by_id = {r["id"]: r for r in response}
            for i in range(len(group)):
                value = by_id.get(i, {}).get("result")
                results.append((value, ref + f"#response_id={i}"))
        return results


def event_from_tx(tx, pool):
    return {"hash": tx["hash"], "block": num(tx["block"]), "log_index": num(tx.get("logIndex", 0)),
            "kind": tx["kind"], "time_utc": tx.get("time_utc"), "raw_ref": tx.get("raw_ref"),
            "time_raw_ref": tx.get("time_raw_ref"), "relayer": tx.get("counterparties", [])[1] if len(tx.get("counterparties", [])) > 1 else None,
            "relayer_fee_raw": tx.get("relayer_fee_raw", "0"), "origin": tx.get("from")}


def event_from_log(log, pool):
    words = [log["data"][i:i + 64] for i in range(2, len(log["data"]), 64)]
    deposit = log["topics"][0].lower() == DEPOSIT
    return {"hash": log["transactionHash"], "block": num(log["blockNumber"]), "log_index": num(log["logIndex"]),
            "kind": "pool_deposit" if deposit else "pool_withdrawal", "time_utc": iso(dt.datetime.fromtimestamp(int(words[1], 16), UTC)) if deposit else None,
            "raw_ref": log["raw_ref"], "time_raw_ref": None,
            "relayer": None if deposit or len(log["topics"]) < 2 else "0x" + log["topics"][1][-40:],
            "relayer_fee_raw": "0" if deposit else str(int(words[2], 16)), "origin": None}


def validate_timeline(d):
    """Reject partial schemas before a malformed live file can abort the run."""
    if not isinstance(d, dict) or not isinstance(d.get("txs"), list) or not isinstance(d.get("coverage"), dict):
        raise ValueError("Incomplete timeline schema (txs/coverage missing)")
    for tx in d["txs"]:
        if not isinstance(tx, dict) or tx.get("kind") == "external" and tx.get("from") and not isinstance(tx.get("hash"), str):
            raise ValueError("Incomplete transaction record")
    if not d.get("tornado_pool"):
        return
    interface = d.get("pool_interface", {})
    if not isinstance(interface.get("asset"), str) or any(k not in interface for k in ("denomination_raw", "decimals", "next_index")):
        raise ValueError("Incomplete pool interface")
    if num(interface["denomination_raw"]) <= 0 or not isinstance(interface["decimals"], int) or not 0 <= interface["decimals"] <= 255:
        raise ValueError("Invalid pool units")
    num(interface["next_index"])
    for b in d.get("daily_balance", []):
        if not isinstance(b, dict) or any(k not in b for k in ("date", "time_utc", "block", "assets", "raw_ref")):
            raise ValueError("Incomplete daily balance sample")
        dt.date.fromisoformat(b["date"])
        parse_time(b["time_utc"])
        num(b["block"])
        for a in b["assets"]:
            if any(k not in a for k in ("asset", "amount", "amount_raw")):
                raise ValueError("Incomplete asset balance")
            num(a["amount_raw"])
            if not math.isfinite(float(a["amount"])):
                raise ValueError("Non-finite asset balance")


def load_inputs():
    ledger = list(csv.DictReader((ROOT / "data/ledger.csv").open()))
    addresses = list(csv.DictReader((ROOT / "data/addresses.csv").open()))
    tornado = [r for r in ledger if r["sdn_name"].upper() == "TORNADO CASH"]
    torn_addresses = sorted({r["address_normalized"].lower() for r in tornado})
    label_rows = list(csv.DictReader((ROOT / "data/labels/labels.csv").open()))
    deployment_labels = [r for r in label_rows if r["source_id"] == "tornado"]
    labelled = collections.defaultdict(list)
    for r in label_rows:
        if r["class"] in {"cex_hot", "cex_deposit", "other_sanctioned", "unknown_service"}:
            labelled[(r["chain"].lower(), r["address_normalized"].lower())].append(r)
    s = {"schema_version": 1, "data_kind": "derived, pinned snapshot of evidence-linked input rows; original raw responses remain referenced", "as_of_utc": iso(dt.datetime.now(UTC)),
         "tornado_ledger": tornado, "ledger_addresses": [r for r in addresses if r["address_normalized"].lower() in torn_addresses],
         "legal_actions": [r for r in csv.DictReader((ROOT / "data/actions.csv").open()) if r["date"] in {v[1] for v in LEGAL}],
         "pools": [], "crosschain": [], "timeline_inventory": [], "unreadable_or_partial": [], "missing_timelines": [], "origins": {}, "other_sanctioned": {},
         "labels": {}, "deployment_labels": deployment_labels, "price_points": {}, "market": [], "legal_balances": [], "fetch_failures": []}
    for r in ledger:
        if r["sdn_name"].upper() != "TORNADO CASH":
            for chain in r.get("chains", r["chain"]).lower().split(";"):
                s["other_sanctioned"].setdefault(chain + ":" + r["address_normalized"].lower(), []).append({k: r.get(k) for k in ("sdn_name", "sdn_uid", "listed_date", "delisted_date", "raw_ref", "listed_raw_ref", "source_url")})
    deployments = {(r["chain"].lower(), r["address_normalized"].lower()): r for r in deployment_labels if r["label"].endswith(" pool") and r["chain"].lower() in EXPLORERS}
    candidates = {(chain, a) for a in torn_addresses for chain in EXPLORERS} | set(deployments)
    for chain, a in sorted(candidates):
        file = ROOT / "data/timelines" / chain / (a + ".json.gz")
        if not file.exists():
            s["missing_timelines"].append({"chain": chain, "address": a, "path": rel(file)})
            continue
        try:
            payload = file.read_bytes()
            d = json.loads(gzip.decompress(payload))
            validate_timeline(d)
            if not isinstance(d, dict) or not isinstance(d.get("txs"), list) or not isinstance(d.get("coverage"), dict):
                raise ValueError("Incomplete timeline schema (txs/coverage missing)")
            if any(not isinstance(t, dict) for t in d["txs"]):
                raise ValueError("Incomplete transaction record")
            if d.get("tornado_pool"):
                interface = d.get("pool_interface", {})
                if any(k not in interface for k in ("asset", "denomination_raw", "decimals", "next_index")):
                    raise ValueError("Incomplete pool interface")
                for t in d["txs"]:
                    if t.get("kind") in {"pool_deposit", "pool_withdrawal"}:
                        if any(k not in t for k in ("hash", "block", "raw_ref", "logIndex")):
                            raise ValueError("Incomplete pool event")
                        num(t["block"])
                        num(t["logIndex"])
        except (OSError, EOFError, ValueError, TypeError) as e:
            s["unreadable_or_partial"].append({"path": rel(file), "reason": type(e).__name__ + ": " + str(e)[:180]})
            continue
        inv = {"chain": chain, "address": a, "timeline_ref": rel(file), "sha256": hashlib.sha256(payload).hexdigest(), "coverage_complete": d["coverage"].get("complete", False),
               "to_block": d["coverage"].get("to_block"), "to_time": d["coverage"].get("to_time"), "tx_rows": len(d["txs"])}
        s["timeline_inventory"].append(inv)
        for tx in d["txs"]:
            if tx.get("kind") == "external" and tx.get("from") and tx.get("success", True):
                s["origins"][chain + ":" + tx["hash"]] = {"address": tx["from"].lower(), "raw_ref": tx.get("raw_ref"), "time_utc": tx.get("time_utc")}
        if chain == "eth" and d.get("tornado_pool"):
            p = {"chain": chain, "address": a, "timeline_ref": rel(file), "interface": d["pool_interface"], "coverage": d.get("log_coverage", {}),
                 "coverage_to_time": d["coverage"].get("to_time"), "daily_balance": d.get("daily_balance", []), "balance_now": d.get("balance_now", []),
                 "balance_observation": d.get("balance_observation"), "validation": d.get("pool_validation"), "events": []}
            p["events"] = [event_from_tx(t, p) for t in d["txs"] if t.get("kind") in {"pool_deposit", "pool_withdrawal"}]
            s["pools"].append(p)
        elif (chain, a) in deployments:
            s["crosschain"].append({**inv, "label": deployments[chain, a], "balance_now": d.get("balance_now", []), "balance_observation": d.get("balance_observation"),
                                    "coverage": d["coverage"], "native_transfer_rows": sum(t.get("asset") == NATIVE[chain] and t.get("success", True) and num(t.get("amount_raw", "0")) > 0 for t in d["txs"])})
    # Already-fetched sanctioned wallets can identify origins without new requests.
    needed = {e["hash"] for p in s["pools"] for e in p["events"] if e["kind"] == "pool_deposit"}
    for key in sorted(s["other_sanctioned"]):
        chain, a = key.split(":", 1)
        if chain != "eth":
            continue
        file = ROOT / "data/timelines/eth" / (a + ".json.gz")
        if not file.exists():
            continue
        try:
            d = read_gz(file)
        except (OSError, EOFError, ValueError):
            continue
        for tx in d.get("txs", []):
            if tx.get("hash") in needed and tx.get("kind") == "external" and tx.get("from") and tx.get("success", True):
                s["origins"]["eth:" + tx["hash"]] = {"address": tx["from"].lower(), "raw_ref": tx.get("raw_ref"), "time_utc": tx.get("time_utc")}
    # Keep only used origins and relevant label claims; do not copy huge label sets.
    s["origins"] = {k: v for k, v in s["origins"].items() if k.split(":", 1)[1] in needed}
    s["labels"] = {c + ":" + a: rows for (c, a), rows in labelled.items() if c == "eth"}
    restore_enrichment(s)
    print(f"Read {len(s['timeline_inventory'])} Tornado-related timelines; {len(s['pools'])} ETH pools; skipped {len(s['unreadable_or_partial'])}", flush=True)
    return s


def uncovered(ranges, completed):
    """Subtract saved immutable log intervals from newly reported missing ranges."""
    remaining = []
    for r in ranges:
        pieces = [(r["from_block"], r["to_block"])]
        for c in completed:
            following = []
            for a, b in pieces:
                if c["to_block"] < a or c["from_block"] > b:
                    following.append((a, b))
                else:
                    if a < c["from_block"]:
                        following.append((a, c["from_block"] - 1))
                    if b > c["to_block"]:
                        following.append((c["to_block"] + 1, b))
            pieces = following
        remaining.extend({**r, "from_block": a, "to_block": b} for a, b in pieces)
    return remaining


def restore_enrichment(s):
    """An offline refresh preserves this analysis's previously fetched primary evidence."""
    if not SNAPSHOT.exists():
        return
    try:
        old = read_gz(SNAPSHOT)
    except (OSError, EOFError, ValueError):
        return
    for key in ("market", "legal_balances", "origin_acquisition", "withdrawal_topic"):
        if key in old:
            s[key] = old[key]
    s["origins"] = {**old.get("origins", {}), **s["origins"]}
    previous = {p["address"]: p for p in old.get("pools", [])}
    for p in s["pools"]:
        prior = previous.get(p["address"])
        if not prior:
            continue
        completed = prior["coverage"].get("supplementary_completed_ranges", [])
        saved = {(e["hash"], e["log_index"]): e for e in prior["events"] if e["block"] <= p["coverage"].get("to_block", 0)}
        for e in p["events"]:
            k = (e["hash"], e["log_index"])
            existing = saved.get(k, {})
            if not e.get("time_utc") and existing.get("time_utc"):
                e["time_utc"] = existing["time_utc"]
                e["time_raw_ref"] = existing.get("time_raw_ref")
            saved[k] = e
        p["events"] = sorted(saved.values(), key=lambda e: (e["block"], e["log_index"]))
        p["coverage"]["supplementary_completed_ranges"] = completed
        p["coverage"]["remaining_missing_ranges"] = uncovered(p["coverage"].get("missing_ranges", []), completed)
        p["coverage"]["complete_after_supplement"] = not p["coverage"]["remaining_missing_ranges"] and bool(p["coverage"])


def anchors_for(s):
    anchors = {}
    for p in s["pools"]:
        for e in p["events"]:
            if e.get("time_utc"):
                anchors[e["block"]] = (e["time_utc"], e.get("time_raw_ref") or e["raw_ref"])
        for b in p["daily_balance"]:
            anchors[b["block"]] = (b["time_utc"], b.get("block_raw_ref") or b["raw_ref"])
    return anchors


def assign_days(s):
    anchors = anchors_for(s)
    blocks = sorted(anchors)
    ambiguous = set()
    for p in s["pools"]:
        for e in p["events"]:
            e.pop("day", None)
            if e.get("time_utc"):
                e["day"] = e["time_utc"][:10]
                e["date_precision"] = "exact timestamp"
                continue
            pos = bisect.bisect_left(blocks, e["block"])
            if pos < len(blocks) and blocks[pos] == e["block"]:
                e["day"] = anchors[blocks[pos]][0][:10]
                e["date_precision"] = "exact block timestamp from another evidenced event or block sample"
                e["day_raw_refs"] = [anchors[blocks[pos]][1]]
            elif 0 < pos < len(blocks) and anchors[blocks[pos - 1]][0][:10] == anchors[blocks[pos]][0][:10]:
                e["day"] = anchors[blocks[pos]][0][:10]
                e["date_precision"] = "UTC date proven by ordered blocks with exact timestamp bounds; intraday time unknown"
                e["day_raw_refs"] = [anchors[blocks[pos - 1]][1], anchors[blocks[pos]][1]]
            else:
                ambiguous.add(e["block"])
    return sorted(ambiguous)


def fill_logs(s, client):
    topic, topic_ref = None, None
    # Reuse the fetcher's evidenced signature: some archive nodes reject the
    # web3 namespace while serving eth_getLogs and archive state successfully.
    for p in s["pools"]:
        for ref in p["coverage"].get("topic_raw_refs", []):
            try:
                saved = read_gz(ROOT / ref.split("#")[0])
                candidate = saved.get("response", {}).get("result")
                if isinstance(candidate, str) and len(candidate) == 66 and candidate.lower() != DEPOSIT:
                    topic, topic_ref = candidate, ref
                    break
            except (OSError, ValueError, AttributeError):
                continue
        if topic:
            break
    if not topic:
        topic, topic_ref = client.rpc("web3_sha3", ["0x" + b"Withdrawal(address,bytes32,address,uint256)".hex()], "https://ethereum-rpc.publicnode.com")
    s["withdrawal_topic"] = {"value": topic, "raw_ref": topic_ref}
    for p in s["pools"]:
        pending = [(r["from_block"], r["to_block"]) for r in p["coverage"].get("remaining_missing_ranges", p["coverage"].get("missing_ranges", []))]
        remaining, completed = [], list(p["coverage"].get("supplementary_completed_ranges", []))
        new_events = []
        while pending:
            low, high = pending.pop()
            try:
                logs, ref = client.rpc("eth_getLogs", [{"address": p["address"], "fromBlock": hex(low), "toBlock": hex(high), "topics": [[DEPOSIT, topic]]}])
                if not isinstance(logs, list):
                    raise RuntimeError("Expected log array")
                completed.append({"from_block": low, "to_block": high, "raw_ref": ref})
                for i, log in enumerate(logs):
                    if not log.get("removed"):
                        log["raw_ref"] = ref + f"#/response/result/{i}"
                        new_events.append(event_from_log(log, p))
            except RuntimeError as e:
                if high - low > 2000 and client.calls < client.budget:
                    mid = (low + high) // 2
                    pending.extend([(mid + 1, high), (low, mid)])
                else:
                    remaining.append({"from_block": low, "to_block": high, "reason": str(e)})
            if client.calls >= client.budget:
                remaining.extend({"from_block": a, "to_block": b, "reason": "request budget"} for a, b in pending)
                break
        all_events = {(e["hash"], e["log_index"]): e for e in p["events"]}
        all_events.update({(e["hash"], e["log_index"]): e for e in new_events})
        p["events"] = sorted(all_events.values(), key=lambda e: (e["block"], e["log_index"]))
        p["coverage"]["supplementary_completed_ranges"] = completed
        p["coverage"]["remaining_missing_ranges"] = remaining
        p["coverage"]["complete_after_supplement"] = not remaining
        if completed:
            print(f"Filled {p['address']}: {len(new_events)} events, {len(remaining)} remaining gaps", flush=True)


def enrich(s, client, max_origins):
    pending = assign_days(s)
    print(f"Withdrawal dates need {len(pending)} distinct block lookups after exact timestamp bounding", flush=True)
    for start in range(0, len(pending), 40):
        heights = pending[start:start + 40]
        try:
            values = client.batch([("eth_getBlockByNumber", [hex(h), False]) for h in heights])
        except RuntimeError as e:
            s["fetch_failures"].append({"stage": "withdrawal dates", "reason": str(e)})
            break
        observed = {h: (iso(dt.datetime.fromtimestamp(num(v["timestamp"]), UTC)), ref) for h, (v, ref) in zip(heights, values) if v}
        for p in s["pools"]:
            for e in p["events"]:
                if not e.get("time_utc") and e["block"] in observed:
                    e["time_utc"], e["time_raw_ref"] = observed[e["block"]]
    assign_days(s)
    # Full-population acquisition in all four +/-30-day event windows, bounded
    # by explicit max_origins. No extrapolation outside this observed subset.
    windows = [(dt.date.fromisoformat(v[1]) - dt.timedelta(days=30), dt.date.fromisoformat(v[1]) + dt.timedelta(days=31)) for v in LEGAL]
    needed = {}
    for p in s["pools"]:
        if p["interface"]["asset"] != "ETH":
            continue
        for e in p["events"]:
            if e["kind"] == "pool_deposit" and e.get("day") and "eth:" + e["hash"] not in s["origins"]:
                day = dt.date.fromisoformat(e["day"])
                if any(low <= day < high for low, high in windows):
                    needed[e["hash"]] = e["day"]
    # Interleave legal windows and pools rather than silently only enriching the
    # first window when the operator-selected cap is smaller than the cohort.
    hashes = sorted(needed, key=lambda h: hashlib.sha256(h.encode()).hexdigest())[:max_origins]
    print(f"Enriching {len(hashes)} of {len(needed)} missing ETH deposit origins in event windows", flush=True)
    for start in range(0, len(hashes), 40):
        group = hashes[start:start + 40]
        try:
            values = client.batch([("eth_getTransactionByHash", [h]) for h in group])
        except RuntimeError as e:
            s["fetch_failures"].append({"stage": "deposit origins", "reason": str(e)})
            break
        for h, (tx, ref) in zip(group, values):
            if tx and tx.get("from"):
                s["origins"]["eth:" + h] = {"address": tx["from"].lower(), "to": tx.get("to"), "raw_ref": ref}
    s["origin_acquisition"] = {"missing_in_event_windows_before_fetch": len(needed), "max_new_origins": max_origins, "selection": "SHA256(transaction hash) order across all ETH pools and legal-event windows; no inference for missing origins"}


def legal_balances(s, client):
    s["legal_balances"] = []
    anchors = anchors_for(s)
    ordered = sorted((parse_time(t).timestamp(), h) for h, (t, _) in anchors.items())
    stamps = [r[0] for r in ordered]
    native = [p for p in s["pools"] if p["interface"]["asset"] == "ETH"]
    targets = [(ident, iso(dt.datetime.combine(dt.date.fromisoformat(day), dt.time(), ET))) for ident, day, _, _ in LEGAL]
    # Paper endpoints use the authors' explicit blocks in addition to the
    # repository's end-of-prior-ET-day checkpoint convention.
    for ident, target in targets:
        timestamp = parse_time(target).timestamp()
        pos = bisect.bisect_left(stamps, timestamp)
        if not 0 < pos < len(ordered):
            continue
        low, high = ordered[pos - 1][1], ordered[pos][1]
        last_ref = None
        while high - low > 1:
            mid = (low + high) // 2
            block, last_ref = client.rpc("eth_getBlockByNumber", [hex(mid), False])
            if num(block["timestamp"]) < timestamp:
                low = mid
            else:
                high = mid
        block, ref = client.rpc("eth_getBlockByNumber", [hex(low), False])
        values = client.batch([("eth_getBalance", [p["address"], hex(low)]) for p in native])
        s["legal_balances"].append({"id": ident, "target_time_utc": target, "block": low, "observed_time_utc": iso(dt.datetime.fromtimestamp(num(block["timestamp"]), UTC)), "block_raw_ref": ref,
                                   "pools": [{"address": p["address"], "amount_raw": str(num(v)), "raw_ref": r} for p, (v, r) in zip(native, values) if v is not None]})
    for ident, height in [("paper_start", 15302392), ("paper_end", 22097863)]:
        block, ref = client.rpc("eth_getBlockByNumber", [hex(height), False])
        values = client.batch([("eth_getBalance", [p["address"], hex(height)]) for p in native])
        s["legal_balances"].append({"id": ident, "block": height, "observed_time_utc": iso(dt.datetime.fromtimestamp(num(block["timestamp"]), UTC)), "block_raw_ref": ref,
                                   "pools": [{"address": p["address"], "amount_raw": str(num(v)), "raw_ref": r} for p, (v, r) in zip(native, values) if v is not None]})


def markets(s, client):
    start = dt.date(2021, 2, 1)
    end = dt.date.fromisoformat(s["as_of_utc"][:10])
    while start < end:
        span = min(500, (end - start).days)
        url = "https://coins.llama.fi/chart/ethereum:" + TORN + "?" + urllib.parse.urlencode({"start": int(dt.datetime.combine(start, dt.time(), UTC).timestamp()), "span": span, "period": "1d"})
        response, ref = client.request(url)
        for coin in response.get("coins", {}).values():
            for i, point in enumerate(coin.get("prices", [])):
                s["market"].append({"time_utc": iso(dt.datetime.fromtimestamp(point["timestamp"], UTC)), "price_usd": point["price"], "raw_ref": ref + f"#price_index={i}", "source_url": url})
        start += dt.timedelta(days=span)
    s["market"] = sorted({r["time_utc"]: r for r in s["market"]}.values(), key=lambda r: r["time_utc"])


def capture_prices(s):
    days = {e["day"] for p in s["pools"] for e in p["events"] if e.get("day")}
    days.update(b["date"] for p in s["pools"] for b in p["daily_balance"])
    assets = {"ETH", "BNB", "POL", "DAI", "USDC", "USDT"}
    for asset in sorted(assets):
        for day in sorted(days):
            close = iso(dt.datetime.combine(dt.date.fromisoformat(day) + dt.timedelta(days=1), dt.time(), UTC))
            price, valued_at, source = usd(asset, close)
            if price is None:
                continue
            hourly = _lookup_rows(asset, "1h", parse_time(close))
            daily = _lookup_rows("MATIC/POL" if asset == "POL" else asset, "1d", parse_time(close))
            row = hourly if hourly and hourly["valuation_time_utc"] == valued_at else daily
            s["price_points"][asset + ":" + day] = {"price_usd": price, "valued_at": valued_at, "source": source, "source_url": row.get("source_url") if row else None, "raw_ref": row.get("raw_ref") if row else None,
                                                       "requested_day_close_utc": close, "exact_day_close": valued_at == close}


def sanctioned_at(s, origin, day):
    return [r for r in s["other_sanctioned"].get("eth:" + origin, []) if r.get("listed_date") and r["listed_date"] <= day and (not r.get("delisted_date") or day < r["delisted_date"])]


def row_complete(p, day):
    # Full-range completeness is deliberately conservative: even an unrelated
    # remaining range prevents a blanket daily completeness assertion.
    return bool(p["coverage"].get("complete_after_supplement", p["coverage"].get("complete", False))) and p.get("deposit_count_matches_interface", False)


def example(p, e):
    result = {"chain": p["chain"], "hash": e["hash"], "explorer_url": EXPLORERS[p["chain"]] + "/tx/" + e["hash"], "pool": p["address"], "event": e["kind"], "day": e.get("day"), "raw_ref": e["raw_ref"]}
    if e.get("day_raw_refs"):
        result["date_raw_refs"] = e["day_raw_refs"]
    return result


DAILY_FIELDS = ["date_utc", "chain", "pool", "asset", "denomination_native", "deposits_count", "withdrawals_count", "deposits_native", "withdrawals_native", "deposits_eth", "withdrawals_eth", "deposits_usd", "withdrawals_usd", "price_usd", "valued_at", "price_requested_close_utc", "price_is_exact_close", "price_raw_ref", "tvl_native", "tvl_eth", "tvl_usd_at_day_close", "tvl_observed_at", "tvl_raw_ref", "unique_deposit_tx_origins_observed", "deposit_events_origin_known", "deposit_events_origin_unknown", "deposits_from_other_sanctioned_count", "deposits_from_other_sanctioned_native", "deposits_from_other_sanctioned_share_count_lower_bound", "deposits_from_cex_labelled_origin_count", "deposits_from_cex_labelled_origin_native", "cex_origin_share_count_lower_bound", "withdrawals_relayer_nonzero_count", "withdrawals_relayer_fee_nonzero_count", "relayer_nonzero_share", "history_complete", "withdrawal_dates_complete", "source_url", "raw_ref"]


def build(s):
    assign_days(s)
    daily = []
    pool_results = []
    all_examples = []
    for p in s["pools"]:
        interface = p["interface"]
        asset = TOKENS.get(interface["asset"].lower(), interface["asset"])
        denomination = num(interface["denomination_raw"]) / 10 ** interface["decimals"]
        groups = collections.defaultdict(list)
        for e in p["events"]:
            if e.get("day"):
                groups[e["day"]].append(e)
        balances = {r["date"]: r for r in p["daily_balance"]}
        total_dep = sum(e["kind"] == "pool_deposit" for e in p["events"])
        total_wdr = len(p["events"]) - total_dep
        p["deposit_count_matches_interface"] = total_dep == interface.get("next_index")
        unknown_dates = sum(not e.get("day") for e in p["events"])
        days = sorted(set(groups) | set(balances))
        for day in days:
            es = groups[day]
            ds = [e for e in es if e["kind"] == "pool_deposit"]
            ws = [e for e in es if e["kind"] == "pool_withdrawal"]
            known = [(e, s["origins"].get("eth:" + e["hash"])) for e in ds]
            known = [(e, origin) for e, origin in known if origin]
            san = [(e, origin, sanctioned_at(s, origin["address"], day)) for e, origin in known if sanctioned_at(s, origin["address"], day)]
            cex = [(e, origin) for e, origin in known if any(r["class"] in {"cex_hot", "cex_deposit"} for r in s["labels"].get("eth:" + origin["address"], []))]
            price = s["price_points"].get(asset + ":" + day, {})
            b = balances.get(day, {})
            principal = next((v for v in b.get("assets", []) if v["asset"] == interface["asset"]), None)
            tvl = float(principal["amount"]) if principal else None
            dep = len(ds) * num(interface["denomination_raw"]) / 10 ** interface["decimals"]
            wdr = len(ws) * num(interface["denomination_raw"]) / 10 ** interface["decimals"]
            pr = price.get("price_usd")
            refs = sorted({e["raw_ref"].split("#")[0] for e in es if e.get("raw_ref")})
            if b.get("raw_ref"):
                refs.append(b["raw_ref"])
            row = {"date_utc": day, "chain": p["chain"], "pool": p["address"], "asset": asset, "denomination_native": denomination,
                   "deposits_count": len(ds), "withdrawals_count": len(ws), "deposits_native": dep, "withdrawals_native": wdr,
                   "deposits_eth": dep if asset == "ETH" else None, "withdrawals_eth": wdr if asset == "ETH" else None,
                   "deposits_usd": dep * pr if pr is not None else None, "withdrawals_usd": wdr * pr if pr is not None else None,
                   "price_usd": pr, "valued_at": price.get("valued_at"), "price_requested_close_utc": price.get("requested_day_close_utc"), "price_is_exact_close": price.get("exact_day_close"), "price_raw_ref": price.get("raw_ref"),
                   "tvl_native": tvl, "tvl_eth": tvl if asset == "ETH" else None, "tvl_usd_at_day_close": tvl * pr if tvl is not None and pr is not None else None,
                   "tvl_observed_at": b.get("time_utc"), "tvl_raw_ref": b.get("raw_ref"), "unique_deposit_tx_origins_observed": len({o["address"] for _, o in known}),
                   "deposit_events_origin_known": len(known), "deposit_events_origin_unknown": len(ds) - len(known), "deposits_from_other_sanctioned_count": len(san),
                   "deposits_from_other_sanctioned_native": len(san) * num(interface["denomination_raw"]) / 10 ** interface["decimals"], "deposits_from_other_sanctioned_share_count_lower_bound": len(san) / len(ds) if ds else None,
                   "deposits_from_cex_labelled_origin_count": len(cex), "deposits_from_cex_labelled_origin_native": len(cex) * num(interface["denomination_raw"]) / 10 ** interface["decimals"], "cex_origin_share_count_lower_bound": len(cex) / len(ds) if ds else None,
                   "withdrawals_relayer_nonzero_count": sum(bool(e.get("relayer") and num(e["relayer"]) != 0) for e in ws),
                   "withdrawals_relayer_fee_nonzero_count": sum(num(e.get("relayer_fee_raw", 0)) > 0 for e in ws), "history_complete": row_complete(p, day),
                   "withdrawal_dates_complete": unknown_dates == 0, "source_url": RPC, "raw_ref": ";".join(sorted(set(refs)))}
            row["relayer_nonzero_share"] = row["withdrawals_relayer_nonzero_count"] / len(ws) if ws else None
            daily.append(row)
            for e, origin, status in san:
                all_examples.append({**example(p, e), "origin": origin, "matched_ofac_entities": status, "kind": "other_sanctioned_origin"})
            for e, origin in cex:
                all_examples.append({**example(p, e), "origin": origin, "labels": s["labels"].get("eth:" + origin["address"], []), "kind": "cex_labelled_origin"})
        pool_results.append({"chain": p["chain"], "address": p["address"], "asset": asset, "denomination": metric(denomination, "native:" + asset),
                             "deposits": metric(total_dep, "events"), "withdrawals": metric(total_wdr, "events"), "undated_events": metric(unknown_dates, "events"),
                             "events_complete": row_complete(p, None), "deposit_count_matches_next_index": total_dep == interface.get("next_index"),
                             "interface_next_index": metric(interface.get("next_index"), "events"), "raw_refs": interface.get("raw_refs"), "timeline_ref": p["timeline_ref"],
                             "coverage": p["coverage"], "latest_balances": p["balance_now"], "latest_balance_observation": p["balance_observation"]})
    daily.sort(key=lambda r: (r["date_utc"], r["chain"], r["pool"]))
    eth = [r for r in daily if r["asset"] == "ETH"]
    native_pools = [p for p in s["pools"] if p["interface"]["asset"] == "ETH"]
    def window(low, high):
        rows = [r for r in eth if low <= r["date_utc"] < high]
        dep = sum(r["deposits_count"] for r in rows)
        wdr = sum(r["withdrawals_count"] for r in rows)
        origins = {s["origins"]["eth:" + e["hash"]]["address"] for p in native_pools for e in p["events"] if e["kind"] == "pool_deposit" and low <= e.get("day", "") < high and "eth:" + e["hash"] in s["origins"]}
        return {"start_inclusive": low, "end_exclusive": high, "deposits": metric(dep, "events"), "withdrawals": metric(wdr, "events"),
                "deposits_eth": metric(math.fsum(r["deposits_native"] for r in rows), "native:ETH"), "withdrawals_eth": metric(math.fsum(r["withdrawals_native"] for r in rows), "native:ETH"),
                "deposits_usd": metric(sum(r["deposits_usd"] or 0 for r in rows), "usd", "sum of each UTC day's flows valued at that day's saved close; see daily CSV valued_at"),
                "withdrawals_usd": metric(sum(r["withdrawals_usd"] or 0 for r in rows), "usd", "sum of each UTC day's flows valued at that day's saved close; see daily CSV valued_at"),
                "usd_unpriced_rows": metric(sum(r["price_usd"] is None for r in rows), "rows"), "unique_tx_origins_observed": metric(len(origins), "addresses"),
                "deposit_events_origin_known": metric(sum(r["deposit_events_origin_known"] for r in rows), "events"), "deposit_events_origin_unknown": metric(sum(r["deposit_events_origin_unknown"] for r in rows), "events"),
                "other_sanctioned_origin_deposits": metric(sum(r["deposits_from_other_sanctioned_count"] for r in rows), "events"), "other_sanctioned_origin_eth": metric(sum(r["deposits_from_other_sanctioned_native"] for r in rows), "native:ETH"),
                "cex_labelled_origin_deposits": metric(sum(r["deposits_from_cex_labelled_origin_count"] for r in rows), "events"), "cex_labelled_origin_eth": metric(sum(r["deposits_from_cex_labelled_origin_native"] for r in rows), "native:ETH"),
                "origin_coverage_share_count": metric(sum(r["deposit_events_origin_known"] for r in rows) / dep if dep else None, "share"),
                "other_sanctioned_origin_share_count_lower_bound": metric(sum(r["deposits_from_other_sanctioned_count"] for r in rows) / dep if dep else None, "share"),
                "direct_cex_labelled_origin_share_count_lower_bound": metric(sum(r["deposits_from_cex_labelled_origin_count"] for r in rows) / dep if dep else None, "share"),
                "nonzero_relayer_share": metric(sum(r["withdrawals_relayer_nonzero_count"] for r in rows) / wdr if wdr else None, "share"),
                "positive_relayer_fee_share": metric(sum(r["withdrawals_relayer_fee_nonzero_count"] for r in rows) / wdr if wdr else None, "share"),
                "all_pool_histories_complete": len(native_pools) == 4 and bool(rows) and all(r["history_complete"] for r in rows), "all_withdrawal_dates_complete": bool(rows) and all(r["withdrawal_dates_complete"] for r in rows)}
    events = []
    for ident, day, title, url in LEGAL:
        day_dt = dt.date.fromisoformat(day)
        before = window((day_dt - dt.timedelta(days=30)).isoformat(), day)
        after = window((day_dt + dt.timedelta(days=1)).isoformat(), (day_dt + dt.timedelta(days=31)).isoformat())
        samples = []
        for p in sorted(native_pools, key=lambda p: num(p["interface"]["denomination_raw"]), reverse=True):
            for e in p["events"]:
                if day < e.get("day", "") < after["end_exclusive"] and e["kind"] == "pool_deposit":
                    samples.append(example(p, e))
                    break
        breakdown = []
        for p in native_pools:
            pool_rows = [r for r in eth if r["pool"] == p["address"]]
            entries = {}
            for label, w in [("before", before), ("after", after)]:
                subset = [r for r in pool_rows if w["start_inclusive"] <= r["date_utc"] < w["end_exclusive"]]
                entries[label] = {"deposits": metric(sum(r["deposits_count"] for r in subset), "events"), "deposits_eth": metric(sum(r["deposits_native"] for r in subset), "native:ETH"), "withdrawals_eth": metric(sum(r["withdrawals_native"] for r in subset), "native:ETH")}
            breakdown.append({"address": p["address"], "denomination": metric(num(p["interface"]["denomination_raw"]) / 1e18, "native:ETH"), **entries})
        events.append({"id": ident, "date": day, "title": title, "source_url": url, "before_30d": before, "after_30d": after, "pool_breakdown": breakdown,
                       "deposit_eth_change_share": metric(after["deposits_eth"]["value"] / before["deposits_eth"]["value"] - 1 if before["deposits_eth"]["value"] else None, "share"),
                       "withdrawal_eth_change_share": metric(after["withdrawals_eth"]["value"] / before["withdrawals_eth"]["value"] - 1 if before["withdrawals_eth"]["value"] else None, "share"), "example_txs": samples[:3],
                       "confidence": "Descriptive before/after comparison, equal UTC windows excluding event date; publication time unknown; not an estimate of causal effect."})
    periods = [window("2019-12-16", "2022-08-08"), window("2022-08-08", "2022-11-08"), window("2022-11-08", "2024-11-26"), window("2024-11-26", "2025-03-21"), window("2025-03-21", s["as_of_utc"][:10])]
    balances = []
    for b in s["legal_balances"]:
        total = sum(num(v["amount_raw"]) for v in b["pools"]) / 1e18
        balances.append({**b, "total_eth": metric(total, "native:ETH"), "pool_count": metric(len(b["pools"]), "contracts")})
    tvl = []
    for day in sorted({r["date_utc"] for r in eth}):
        rows = [r for r in eth if r["date_utc"] == day and r["tvl_eth"] is not None]
        if len(rows) == len(native_pools):
            tvl.append({"date": day, "eth": metric(sum(r["tvl_eth"] for r in rows), "native:ETH"), "observed_times_utc": sorted({r["tvl_observed_at"] for r in rows}), "raw_refs": [r["tvl_raw_ref"] for r in rows]})
    market_events = []
    for ident, day, _, _ in LEGAL:
        target = parse_time(day + "T00:00:00Z")
        points = {}
        for offset, label in [(-1, "day_before"), (0, "event_day"), (1, "day_after"), (7, "day_plus_7"), (30, "day_plus_30")]:
            stamp = target + dt.timedelta(days=offset)
            candidates = [r for r in s["market"] if r["time_utc"][:10] == stamp.date().isoformat()]
            if candidates:
                r = candidates[-1]
                points[label] = {"price": metric(r["price_usd"], "usd_per_TORN", r["time_utc"]), "raw_ref": r["raw_ref"], "source_url": r["source_url"]}
        before = points.get("day_before", {}).get("price", {}).get("value")
        after = points.get("day_after", {}).get("price", {}).get("value")
        market_events.append({"id": ident, "points": points, "day_before_to_day_after_change_share": metric(after / before - 1 if before and after else None, "share")})
    coverage = {"ledger_rows": metric(len(s["tornado_ledger"]), "address_entity_rows"), "distinct_ledger_addresses": metric(len({r["address_normalized"] for r in s["tornado_ledger"]}), "addresses"),
                "ledger_chain_address_pairs": metric(len(s["ledger_addresses"]), "addresses"), "ledger_addresses_with_readable_listed_chain_timelines": metric(sum(any(i["chain"] == r["chain"].lower() and i["address"] == r["address_normalized"].lower() for i in s["timeline_inventory"]) for r in s["ledger_addresses"]), "addresses"),
                "readable_tornado_related_timeline_files": metric(len(s["timeline_inventory"]), "files"), "unreadable_or_partial_files_skipped": metric(len(s["unreadable_or_partial"]), "files"),
                "eth_pools": metric(len(s["pools"]), "contracts"), "eth_native_pools": metric(len(native_pools), "contracts"), "eth_native_events": metric(sum(len(p["events"]) for p in native_pools), "events"),
                "undated_eth_native_events": metric(sum(not e.get("day") for p in native_pools for e in p["events"]), "events"), "all_pools_events_complete": bool(pool_results) and all(p["events_complete"] for p in pool_results),
                "skipped_files": s["unreadable_or_partial"], "missing_timelines": s["missing_timelines"], "timeline_inventory": s["timeline_inventory"],
                "notes": ["All Tornado ledger entries use ETH in the current ledger; BSC/Polygon/Arbitrum/OP deployment activity is separate same-address/other-chain evidence, not an additional OFAC chain designation.",
                          "Unique depositors means distinct evidenced top-level transaction origins, a lower bound on origin addresses and never a count of people. Contract callers and economic depositors can differ.",
                          "CEX-labelled origin is a direct transaction-origin label match only. One-hop CEX withdrawal funding of unlabelled depositors is unmeasured; unknown origins and unlabelled senders are not clean funds.",
                          "Pool TVL samples retain their actual observation time. USD at day close revalues that sample, not an independently observed closing balance.",
                          "Daily missing/unreadable inputs are not zero activity. Full log coverage and date assignment are separately reported."]}
    result = {"job": "tornado", "schema_version": 1, "provisional": True, "as_of_utc": s["as_of_utc"], "script": "scripts/analysis/tornado.py", "input_snapshot": rel(SNAPSHOT),
              "coverage": coverage, "legal_events": events, "legal_action_evidence": s["legal_actions"], "periods": periods, "pools": pool_results, "legal_checkpoint_balances": balances,
              "native_pool_tvl_daily": tvl, "counterparty_examples": all_examples, "same_address_other_chain": s["crosschain"],
              "torn_token": {"address": TORN, "asset_unit": "TORN token, distinct from ETH pool principal", "listed_ledger_rows": [r for r in s["tornado_ledger"] if r["address_normalized"] == TORN], "daily_price_points": metric(len(s["market"]), "observations"), "event_comparisons": market_events, "price_method": "DefiLlama daily sampled token prices, each with actual timestamp; not guaranteed day closes. No liquidity, market-cap or pool-principal inference."},
              "prior_art_comparison": {"source_url": "https://arxiv.org/pdf/2507.11721v2", "raw_ref": "data/raw/priorart/papers/arxiv-2507-11721-v2.pdf.gz", "initial_170_address_balance": metric(499769.74, "native:ETH"), "end_170_address_balance": metric(145579.38, "native:ETH"),
                                       "tornado_initial_share_reported": metric(.4417, "share"), "tornado_end_share_reported": metric(.9912, "share"), "deposit_volume_drop_reported": metric(.7103, "share"), "warning": "The paper's 170-address balances cannot be compared as if they were the four ETH pools. Pool-share-implied balances use rounded shares and are approximate. Paper block endpoints are separately queried."},
              "fetch_failures": s["fetch_failures"], "source_error_observations": s.get("source_error_observations", []), "methods": {"daily_timezone": "UTC", "checkpoint_timezone": "America/New_York", "legal_publication_time": "unknown within action date; no hour-level causal claims", "pool_principal": "One denomination per Deposit/Withdrawal event; withdrawal principal includes any relayer fee. Never add an internal value transfer to its pool event.", "relayer_use": "Nonzero indexed Withdrawal relayer field; positive relayer fee is a separate statistic; either can differ from submitting transaction sender.", "date_assignment": "Exact event/block timestamp where available; otherwise UTC date only when preceding/following exact timestamp anchors agree on UTC date. Remaining ambiguous dates excluded and counted.", "provisional": "Shared fetchers are still running; pinned snapshot makes --check reproducible independently of live timeline replacement."},
              "disclaimer": "Research, not legal or compliance advice. Receipt from a sanctioned address does not establish wrongdoing. Labels are leads; no controller inference."}
    paper_before = sum(num(p["interface"]["denomination_raw"]) * sum(e["kind"] == "pool_deposit" and e["block"] < 15302392 for e in p["events"]) for p in native_pools) / 1e18
    paper_during = sum(num(p["interface"]["denomination_raw"]) * sum(e["kind"] == "pool_deposit" and 15302392 <= e["block"] <= 22097863 for e in p["events"]) for p in native_pools) / 1e18
    result["prior_art_comparison"].update({"four_pool_deposits_before_paper_start_block": metric(paper_before, "native:ETH"),
                                         "four_pool_deposits_within_paper_blocks_inclusive": metric(paper_during, "native:ETH"),
                                         "four_pool_deposit_change_share": metric(paper_during / paper_before - 1 if paper_before else None, "share"),
                                         "paper_start_tornado_balance_implied_by_rounded_share": metric(499769.74 * .4417, "native:ETH"),
                                         "paper_end_tornado_balance_implied_by_rounded_share": metric(145579.38 * .9912, "native:ETH")})
    result["findings"] = findings(result, s)
    return result, daily


def findings(r, s):
    """Reviewable headline candidates, each carrying units and illustrative txs."""
    by_id = {e["id"]: e for e in r["legal_events"]}
    out = []
    for ident in ("delisting", "designation", "van_loon", "redesignation"):
        e = by_id[ident]
        a, b = e["after_30d"], e["before_30d"]
        change = e["deposit_eth_change_share"]["value"]
        if change is None:
            continue
        statement = f"{e['title']}: ETH deposits changed {change:+.2%} in equal 30-day windows ({b['deposits_eth']['value']:,.1f} → {a['deposits_eth']['value']:,.1f} ETH)."
        out.append({"id": "tornado_" + ident, "sentence": statement, "number": e["deposit_eth_change_share"], "before": b["deposits_eth"], "after": a["deposits_eth"],
                    "unique_tx_origins_before": b["unique_tx_origins_observed"], "unique_tx_origins_after": a["unique_tx_origins_observed"],
                    "origins_observed_for_all_deposits_in_both_windows": b["deposit_events_origin_unknown"]["value"] == 0 and a["deposit_events_origin_unknown"]["value"] == 0,
                    "example_txs": e["example_txs"], "confidence": e["confidence"] + " Counts cross-checked against pool nextIndex; source gaps remain explicit in coverage.", "script": "scripts/analysis/tornado.py"})
    e = by_id["delisting"]
    large = next((p for p in e["pool_breakdown"] if p["denomination"]["value"] == 100), None)
    if large and e["after_30d"]["deposits_eth"]["value"]:
        p = next(p for p in s["pools"] if p["address"] == large["address"])
        samples = []
        for ev in p["events"]:
            if ev["kind"] == "pool_deposit" and e["after_30d"]["start_inclusive"] <= ev.get("day", "") < e["after_30d"]["end_exclusive"] and ev["hash"] not in {t["hash"] for t in samples}:
                samples.append(example(p, ev))
                if len(samples) == 3:
                    break
        share = large["after"]["deposits_eth"]["value"] / e["after_30d"]["deposits_eth"]["value"]
        out.insert(1, {"id": "tornado_rebound_large_pool", "sentence": f"The 100 ETH pool supplied {share:.2%} of ETH deposited in the post-delisting 30-day window; its Deposit count rose from {large['before']['deposits']['value']} to {large['after']['deposits']['value']}.", "number": metric(share, "share"), "pool_breakdown": e["pool_breakdown"], "example_txs": samples, "confidence": "High for event counts and native ETH denominations. Denomination concentration does not identify people, ownership or the purpose of deposits.", "script": "scripts/analysis/tornado.py"})
    token = next(m for m in r["torn_token"]["event_comparisons"] if m["id"] == "van_loon")
    if token["day_before_to_day_after_change_share"]["value"] is not None and by_id["van_loon"]["deposit_eth_change_share"]["value"] is not None:
        e = by_id["van_loon"]
        out.insert(1, {"id": "tornado_token_vs_use", "sentence": f"Around Van Loon, sampled TORN price rose {token['day_before_to_day_after_change_share']['value']:.2%}; ETH deposits in the surrounding 30-day windows rose {e['deposit_eth_change_share']['value']:.2%}.",
                       "number": token["day_before_to_day_after_change_share"], "price_before": token["points"]["day_before"], "price_after": token["points"]["day_after"], "deposit_change": e["deposit_eth_change_share"],
                       "example_txs": e["example_txs"], "confidence": "Different time horizons: price uses explicitly timestamped November 25/27 samples, protocol use uses equal 30-day windows. Market data is not inferred from these illustrative pool transactions. Descriptive, not causal.", "script": "scripts/analysis/tornado.py"})
    checkpoints = {b["id"]: b for b in r["legal_checkpoint_balances"]}
    if r["native_pool_tvl_daily"] and "paper_end" in checkpoints:
        latest = r["native_pool_tvl_daily"][-1]
        prior = checkpoints["paper_end"]
        samples = []
        for p in sorted([p for p in s["pools"] if p["interface"]["asset"] == "ETH"], key=lambda p: num(p["interface"]["denomination_raw"]), reverse=True):
            candidates = [e for e in p["events"] if e["kind"] == "pool_deposit" and e.get("day") == latest["date"]]
            if candidates:
                samples.append(example(p, candidates[0]))
        out.insert(2, {"id": "tornado_balance_recovery", "sentence": f"Four classic ETH pools held {latest['eth']['value']:,.1f} ETH at {', '.join(latest['observed_times_utc'])}, versus {prior['total_eth']['value']:,.1f} ETH at the paper's March 2025 endpoint block.",
                       "number": latest["eth"], "at_paper_endpoint": prior["total_eth"], "growth_share": metric(latest["eth"]["value"] / prior["total_eth"]["value"] - 1, "share"),
                       "raw_refs": latest["raw_refs"] + [p["raw_ref"] for p in prior["pools"]], "observed_at": latest["observed_times_utc"], "example_txs": samples[:3],
                       "confidence": "High for native balances at the stated blocks. Examples illustrate contemporary pool deposits, not the complete net change. This is stock, not gross flow, seized value or legal-compliance measurement.", "script": "scripts/analysis/tornado.py"})
    return out


def csv_text(rows):
    f = io.StringIO(newline="")
    writer = csv.DictWriter(f, fieldnames=DAILY_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return f.getvalue()


def render_doc(r):
    cv = r["coverage"]
    text = ["# Tornado Cash — provisional legal-event case study", "", f"Snapshot: {r['as_of_utc']}. `provisional: true`. Rebuild with `.venv/bin/python scripts/analysis/tornado.py`; add `--fetch` for cached keyless gap filling. Reproduce the pinned snapshot with `--check` while shared fetchers continue running.", "",
            f"Coverage: **{cv['ledger_addresses_with_readable_listed_chain_timelines']['value']} / {cv['ledger_chain_address_pairs']['value']} ledger chain–addresses** have readable timelines. {cv['readable_tornado_related_timeline_files']['value']} readable Tornado-related timeline files across five checked chains; {cv['unreadable_or_partial_files_skipped']['value']} unreadable/partial files skipped. {cv['eth_pools']['value']} identified ETH-chain pool contracts, including {cv['eth_native_pools']['value']} native ETH pools. {cv['undated_eth_native_events']['value']} native-pool events still lack a proven UTC date.", "",
            "## What changed around each legal event?", "", "Equal 30-day UTC windows exclude the event date. These are descriptive changes, not causal estimates. Native ETH amounts count pool principal; USD revalues each day's flow at its saved closing observation. The complete per-pool series, actual price times, independent TVL observation times and raw references are in `data/derived/tornado_daily.csv`.", "",
            "| Event | Deposits before, ETH | Deposits after, ETH | Change | Withdrawals before, ETH | Withdrawals after, ETH | Nonzero relayer share before → after |", "|---|---:|---:|---:|---:|---:|---:|"]
    for e in r["legal_events"]:
        b, a = e["before_30d"], e["after_30d"]
        percent = e["deposit_eth_change_share"]["value"]
        percent_text = f"{percent:+.2%}" if percent is not None else "unavailable"
        text.append(f"| [{e['date']}]({e['source_url']}) {e['title']} | {b['deposits_eth']['value']:,.1f} | {a['deposits_eth']['value']:,.1f} | {percent_text} | {b['withdrawals_eth']['value']:,.1f} | {a['withdrawals_eth']['value']:,.1f} | {b['nonzero_relayer_share']['value'] or 0:.1%} → {a['nonzero_relayer_share']['value'] or 0:.1%} |")
    text += ["", "The formal removal has the largest positive native-volume change among these equal-window comparisons. The ruling coincides with a much larger reaction in TORN's sampled market price than in ETH deposits. At the initial designation, fewer distinct transaction origins and higher withdrawals accompany the fall in deposits; these observations do not isolate sanctions from other causes.", "", "### Candidate findings and transaction examples", ""]
    for f in r.get("findings", []):
        text += [f"- **{f['sentence']}** Confidence: {f['confidence']}"]
        for price_key in ("price_before", "price_after"):
            if price_key in f:
                v = f[price_key]
                text.append(f"  - Market evidence: {v['price']['value']} USD/TORN, valued at {v['price']['valued_at']}; `{v['raw_ref']}`.")
        if f.get("raw_refs"):
            text.append("  - Balance evidence: " + "; ".join(f"`{v}`" for v in f["raw_refs"]) + ".")
        for tx in f["example_txs"]:
            text.append(f"  - [{tx['hash']}]({tx['explorer_url']}) ({tx['day']}, pool `{tx['pool']}`); `{tx['raw_ref']}`.")
    origins_complete = cv["eth_native_pools"]["value"] == 4 and all(e[w]["deposit_events_origin_unknown"]["value"] == 0 for e in r["legal_events"] for w in ("before_30d", "after_30d"))
    origin_note = "All observed Deposit events in the eight comparison windows have an evidenced origin." if origins_complete else "Missing origins remain explicit; these are observed lower bounds."
    text += ["", "### Event-window depositors", "", "Origins are distinct top-level transaction sender addresses, not people. " + origin_note + " Elsewhere the daily CSV explicitly preserves missing origins.", "", "| Event | Before, origin addresses | After, origin addresses | Before, Deposit events with known origin / all | After, Deposit events with known origin / all |", "|---|---:|---:|---:|---:|"]
    for e in r["legal_events"]:
        b, a = e["before_30d"], e["after_30d"]
        text.append(f"| {e['date']} | {b['unique_tx_origins_observed']['value']:,} | {a['unique_tx_origins_observed']['value']:,} | {b['deposit_events_origin_known']['value']:,} / {b['deposits']['value']:,} | {a['deposit_events_origin_known']['value']:,} / {a['deposits']['value']:,} |")
    text += ["", "## Independent pool balances and comparison with arXiv 2507.11721", "", "The paper reports 499,769.74 ETH at designation and 145,579.38 ETH at its March 2025 endpoint **across 170 addresses**, not solely Tornado. Its rounded Tornado shares (44.17% and 99.12%) imply approximately 220,748.29 ETH and 144,298.28 ETH. Those approximations are not exact published pool balances. We query the paper's explicit start/end blocks as well as the project's prior-ET-day-end checkpoint. Primary evidence and actual block times follow.", "", "| Checkpoint | Block | Actual observation UTC | Four native-pool balance, ETH |", "|---|---:|---|---:|"]
    for b in r["legal_checkpoint_balances"]:
        text.append(f"| {b['id']} | {b['block']} | {b['observed_time_utc']} | {b['total_eth']['value']:,.1f} ({b['pool_count']['value']} pools) |")
    text += ["", "Checkpoint raw responses (each contains the exact block and request):"]
    for b in r["legal_checkpoint_balances"]:
        text.append(f"- {b['id']}: block `{b['block_raw_ref']}`; balances " + "; ".join(f"`{p['raw_ref']}`" for p in b["pools"]) + ".")
    art = r["prior_art_comparison"]
    if art["four_pool_deposit_change_share"]["value"] is not None:
        text += ["", f"At the paper's exact inclusive block window, we observe {art['four_pool_deposits_before_paper_start_block']['value']:,.1f} ETH deposited before the start block and {art['four_pool_deposits_within_paper_blocks_inclusive']['value']:,.1f} ETH within the sanctions window: a {art['four_pool_deposit_change_share']['value']:+.2%} change in gross deposit volume, against the paper's reported −71.03%. The paper's stated 957 days counts its endpoint convention; our UTC calendar periods are half-open and put 2025-03-21 in the delisted period. The cohort and endpoint conventions must be retained when quoting either comparison.", "", "The four-pool paper-end balance is close to, but not identical with, the balance implied by the paper's rounded Tornado share. Its 170-address balance is a different denominator. The four-pool start balance also differs from that implied share; the source does not specify an identical pool-only cohort, so this is a partial reconciliation, not an exact independent reproduction of its aggregate."]
    tvl = r["native_pool_tvl_daily"]
    if tvl:
        last = tvl[-1]
        text += ["", f"Latest common daily sample: **{last['eth']['value']:,.1f} ETH**, observed at {', '.join(last['observed_times_utc'])}. This is a direct balance observation, independent of gross flows. Its evidence: " + "; ".join(f"`{x}`" for x in last["raw_refs"]) + "."]
    text += ["", "## Depositors, other sanctioned origins, and CEX withdrawals", "", "The daily CSV reports distinct **observed top-level transaction origins**, not people or verified economic depositors. The known-origin denominator is explicit for every pool/day. The same origin can use several pools; window totals deduplicate it. A listed address match requires its OFAC listing date to be no later than the deposit date and precedes any recorded delisting. Tornado's own contracts are excluded from the other-sanctioned cohort. Later listings are not backdated.", "", "A CEX-labelled origin is a direct transaction-sender label match. We have not reconstructed one-hop exchange-withdrawal funding of otherwise unlabelled depositors. Therefore the full share of deposits funded by CEX withdrawals is **unknown**, not zero. All label matches are evidence leads, not allegations about who controls the depositor or whether an exchange acted unlawfully.", "", "| Period [start, end) | Deposit events | Origins known, events | Unique origins observed, addresses | Other-sanctioned-origin deposits, events | Other-sanctioned-origin principal, ETH | Direct CEX-labelled origin, events |", "|---|---:|---:|---:|---:|---:|---:|"]
    for p in r["periods"]:
        text.append(f"| {p['start_inclusive']} – {p['end_exclusive']} | {p['deposits']['value']:,} | {p['deposit_events_origin_known']['value']:,} | {p['unique_tx_origins_observed']['value']:,} | {p['other_sanctioned_origin_deposits']['value']:,} | {p['other_sanctioned_origin_eth']['value']:,.1f} | {p['cex_labelled_origin_deposits']['value']:,} |")
    for ex in r["counterparty_examples"][:6]:
        text += ["", f"Example {ex['kind']}: [{ex['hash']}]({ex['explorer_url']}); origin `{ex['origin']['address']}`; `{ex['raw_ref']}`; origin evidence `{ex['origin']['raw_ref']}`."]
    text += ["", "## TORN is a token, not pool ETH", "", f"The TORN token contract `{TORN}` appears in the replacement OFAC entry (2022-11-08 → 2025-03-21). Token prices below are DefiLlama daily samples at their actual times, **not asserted exchange closing prices**. Token price changes do not measure pool TVL, transaction count, economic ownership or legal compliance.", "", "| Legal event | Price before, USD/TORN | Price after, USD/TORN | Change |", "|---|---:|---:|---:|"]
    for m in r["torn_token"]["event_comparisons"]:
        b, a = m["points"].get("day_before"), m["points"].get("day_after")
        if b and a:
            text.append(f"| {m['id']} | {b['price']['value']:,.4f} at {b['price']['valued_at']} | {a['price']['value']:,.4f} at {a['price']['valued_at']} | {m['day_before_to_day_after_change_share']['value']:+.2%} |")
        else:
            text.append(f"| {m['id']} | unavailable | unavailable | unavailable |")
    text += ["", "## Same address, other chain", "", "The current ledger assigns every Tornado identifier to ETH. The pinned Tornado deployment configuration separately identifies BSC, Polygon, Arbitrum and Optimism pools. The identical address string can have a different denomination or asset on another chain. Their native balances below are **never summed with ETH mainnet**. Ordinary account-history rows are not relabelled as pool events; complete Deposit/Withdrawal series on these chains remain a gap.", "", "| Chain | Pool | Deployment label | Native balance, native units | Balance block | History complete |", "|---|---|---|---:|---:|---|"]
    for c in r["same_address_other_chain"]:
        b = next((b for b in c["balance_now"] if b["asset"] == NATIVE[c["chain"]]), {})
        text.append(f"| {c['chain']} | `{c['address']}` | {c['label']['label']} | {b.get('amount', 'unknown')} {NATIVE[c['chain']]} | {b.get('block', c.get('to_block'))} | {c['coverage_complete']} |")
    text += ["", "## Coverage, reproducibility and confidence", ""]
    text += ["- " + note for note in cv["notes"]]
    text += ["- `--check` uses the pinned, compressed input snapshot; it recomputes JSON and daily CSV and compares exact outputs. A normal rerun reads the newest available timelines and replaces the provisional snapshot. Shared source files are never edited.", "- Missing timeline files, malformed gzip/JSON, and partial schemas are counted individually. Pool-event gaps and unresolved withdrawal dates remain visible. No missing observation becomes a zero balance.", "- Deposit dates come from events; withdrawal UTC dates can also be proved by bounding block timestamps. Such a date is exact even when its intraday time remains unknown. Bounds and exact source references are preserved in the pinned snapshot.", "- Native-principal events exclude unrelated tokens, unsolicited transfers and administration calls. DAI/USDT/USDC pool units remain separate; cDAI/cUSDC and WBTC are not automatically valued using a different token's price.", "- Before/after windows can be affected by market conditions, exploits, service substitution and simultaneous news. November 2022 is a withdrawal and immediate re-designation, not an ordinary unsanctioned interval. The Fifth Circuit ruling is a distinct legal milestone from OFAC's March 2025 removal.",  "",  "", "Research, not legal or compliance advice. Labels are leads. A factual on-chain receipt does not establish wrongdoing.", ""]
    if r["fetch_failures"]:
        text += ["### Acquisition gaps", ""] + ["- `" + json.dumps(f, sort_keys=True) + "`" for f in r["fetch_failures"]]
    return "\n".join(text)


def self_test():
    # Synthetic checks target financial semantics, not implementation mirroring.
    p = {"events": [{"block": 1, "time_utc": "2025-03-20T23:59:00Z", "raw_ref": "a"}, {"block": 3, "time_utc": "2025-03-21T00:01:00Z", "raw_ref": "b"}, {"block": 2, "time_utc": None, "raw_ref": "c"}, {"block": 4, "time_utc": "2025-03-21T00:02:00Z", "raw_ref": "d"}, {"block": 5, "time_utc": None, "raw_ref": "e"}, {"block": 6, "time_utc": "2025-03-21T00:03:00Z", "raw_ref": "f"}], "daily_balance": []}
    s = {"pools": [p]}
    assert assign_days(s) == [2], "Do not invent dates across midnight"
    assert p["events"][4]["day"] == "2025-03-21", "Same-day exact bounds prove UTC date"
    status = {"other_sanctioned": {"eth:a": [{"listed_date": "2022-08-08", "delisted_date": "2025-03-21"}]}}
    assert not sanctioned_at(status, "a", "2022-08-07")
    assert sanctioned_at(status, "a", "2022-08-08")
    assert not sanctioned_at(status, "a", "2025-03-21")
    assert iso(dt.datetime(2022, 8, 8, tzinfo=ET)) == "2022-08-08T04:00:00Z"
    assert uncovered([{"from_block": 1, "to_block": 10}], [{"from_block": 3, "to_block": 7}]) == [{"from_block": 1, "to_block": 2}, {"from_block": 8, "to_block": 10}]
    assert not row_complete({"coverage": {"complete": True}, "deposit_count_matches_interface": False}, None), "A truncated log response must not be declared complete"
    withdrawal = {"data": "0x" + "1".zfill(64) + "2".zfill(64) + "5".zfill(64), "topics": ["0xwithdrawal", "0x" + "3".zfill(64)], "transactionHash": "0xtest", "blockNumber": "0x10", "logIndex": "0x1", "raw_ref": "synthetic"}
    decoded = event_from_log(withdrawal, {})
    assert decoded["relayer_fee_raw"] == "5" and decoded["relayer"] == "0x" + "3".zfill(40)
    for partial in ({}, {"txs": [None], "coverage": {}}, {"txs": [{"kind": "external", "from": "a"}], "coverage": {}}):
        try:
            validate_timeline(partial)
        except ValueError:
            pass
        else:
            raise AssertionError("Partial timeline must be rejected for counted skipping")
    print("Self-test passed: midnight ambiguity, same-day bounds, historical listing intervals, ET checkpoints, gap subtraction, count completeness, relayer ABI")


def resolve_ref(ref):
    path, _, fragment = ref.partition("#")
    value = read_gz(ROOT / path)
    if fragment.startswith("/"):
        for part in fragment.lstrip("/").split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            value = value[int(part)] if isinstance(value, list) else value[part]
    elif fragment.startswith("response_id="):
        identity = int(fragment.split("=", 1)[1])
        value = next(r["result"] for r in value["response"] if r["id"] == identity)
    return value


def validate_saved_evidence(s):
    """Check primary log samples and every independently queried checkpoint."""
    checked = 0
    refs = {e["raw_ref"].split("#")[0] for p in s["pools"] for e in p["events"]}
    missing = [r for r in refs if not (ROOT / r).is_file()]
    if missing:
        raise ValueError("Missing primary raw evidence: " + str(missing[:3]))
    for p in s["pools"]:
        ids = [(e["hash"], e["log_index"]) for e in p["events"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate pool event identities: " + p["address"])
        # At least one deposit and one withdrawal per nonempty pool, selected
        # deterministically without trusting the rendered headline examples.
        for kind in ("pool_deposit", "pool_withdrawal"):
            es = [e for e in p["events"] if e["kind"] == kind]
            if not es:
                continue
            e = min(es, key=lambda e: hashlib.sha256(e["hash"].encode()).hexdigest())
            log = resolve_ref(e["raw_ref"])
            decoded = event_from_log({**log, "raw_ref": e["raw_ref"]}, p)
            for key in ("hash", "block", "log_index", "kind", "relayer_fee_raw"):
                if decoded[key] != e[key]:
                    raise ValueError("Raw ABI/sample mismatch: " + e["raw_ref"] + " " + key)
            if log["address"].lower() != p["address"]:
                raise ValueError("Wrong pool in primary log")
            checked += 1
    for checkpoint in s["legal_balances"]:
        block = resolve_ref(checkpoint["block_raw_ref"])["response"]["result"]
        if num(block["number"]) != checkpoint["block"] or iso(dt.datetime.fromtimestamp(num(block["timestamp"]), UTC)) != checkpoint["observed_time_utc"]:
            raise ValueError("Checkpoint block mismatch")
        for p in checkpoint["pools"]:
            if num(resolve_ref(p["raw_ref"])) != num(p["amount_raw"]):
                raise ValueError("Checkpoint balance mismatch")
            checked += 1
    print(f"Validated {checked} canonical log/checkpoint observations; all {len(refs)} primary log response files exist")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--resume-fetch", action="store_true", help="Enrich pinned input snapshot without rereading changing timelines")
    parser.add_argument("--from-snapshot", action="store_true", help="Rebuild outputs offline from pinned inputs without rereading live sources")
    parser.add_argument("--request-budget", type=int, default=700)
    parser.add_argument("--max-origins", type=int, default=12000)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.check or args.from_snapshot:
        s = read_gz(SNAPSHOT)
    else:
        s = read_gz(SNAPSHOT) if args.resume_fetch else load_inputs()
        if args.fetch or args.resume_fetch:
            s["fetch_failures"] = []
            client = EvidenceClient(args.request_budget)
            for name, task in [("pool logs", lambda: fill_logs(s, client)), ("legal balances", lambda: legal_balances(s, client)), ("TORN market", lambda: markets(s, client)), ("withdrawal dates and origins", lambda: enrich(s, client, args.max_origins))]:
                try:
                    task()
                except RuntimeError as e:
                    s["fetch_failures"].append({"stage": name, "reason": str(e)})
                    print(f"Gap: {name}: {e}", flush=True)
            s["source_error_observations"] = s.get("source_error_observations", []) + client.failures
        assign_days(s)
        capture_prices(s)
        write_gz(SNAPSHOT, s)
    r, rows = build(s)
    from scripts.lib.fetch_status import apply_status, report_status
    r = apply_status(r, ROOT, "tornado")
    r["input_snapshot_sha256"] = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    serialized = json.dumps(r, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    table = csv_text(rows)
    if args.check:
        validate_saved_evidence(s)
        problems = []
        if not OUT.exists() or OUT.read_text() != serialized:
            problems.append(rel(OUT))
        if not DAILY.exists() or DAILY.read_text() != table:
            problems.append(rel(DAILY))
        if not DOC.exists() or DOC.read_text() != report_status(render_doc(r), r):
            problems.append(rel(DOC))
        if problems:
            print("Reproduction mismatch: " + ", ".join(problems))
            return 1
        print(f"Reproduced provisional JSON and {len(rows):,} pool-day rows from pinned evidence snapshot")
        return 0
    for path, content in [(OUT, serialized), (DAILY, table), (DOC, report_status(render_doc(r), r))]:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        tmp.replace(path)
    print(f"Wrote {rel(OUT)}, {len(rows):,} daily rows, {rel(DOC)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
