#!/usr/bin/env python3
"""Eight evidence-linked case timelines. Offline, rerunnable during acquisition.

Run with the project Python. --check recomputes both outputs from the current
saved inputs, failing on changed evidence as well as changed published results.
--self-test exercises accounting, streaming/partial-file handling and ET dates.
No network, keys, dependencies, snapshots or writes outside the three job paths.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, getcontext
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.prices import price  # reviewed read-only usd() path
from scripts.labels.lookup import label as lookup_label

getcontext().prec = 70
UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
OUT = ROOT / "results/cases.json"
DOC = ROOT / "docs/analysis/CASES.md"
SCRIPT = "scripts/analysis/cases.py"
SELECTION = ["tornado-cash", "lazarus-ronin", "garantex-grinex",
             "hamas-tron-aljebouri", "sinbad", "suex",
             "samsam-first-addresses", "cryptex-pm2btc"]
CLASSIC = {"0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc",
           "0x47ce0c6ed5b0ce3d3a51fdb1c52dc66a7c3c2936",
           "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf",
           "0xa160cdab225685da1d56aa342ad8841c3b53f291"}
NATIVE = {"ETH": "ETH", "BTC": "BTC", "TRX": "TRX", "LTC": "LTC"}
# Identity is contract + chain + decimals, never an explorer-supplied symbol.
TOKENS = {
    ("ETH", "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"): ("USDC", 6),
    ("ETH", "0xdac17f958d2ee523a2206206994597c13d831ec7"): ("USDT", 6),
    ("ETH", "0x6b175474e89094c44da98b954eedeac495271d0f"): ("DAI", 18),
    ("TRX", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"): ("USDT", 6),
}
ADD = {"AddedBlackList", "Blacklisted"}
REMOVE = {"RemovedBlackList", "UnBlacklisted"}
BURN = {"DestroyedBlackFunds"}


def iso(t):
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def timeof(s):
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return (t.replace(tzinfo=UTC) if t.tzinfo is None else t).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def day_bounds(date):
    # End is exclusive; use end - one second for the specified publication range.
    d = dt.date.fromisoformat(date[:10])
    start = dt.datetime.combine(d, dt.time(), ET)
    end = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(), ET)
    noon = dt.datetime.combine(d, dt.time(12), ET)
    return start.astimezone(UTC), noon.astimezone(UTC), end.astimezone(UTC)


def dec(x):
    try:
        d = Decimal(str(x))
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def number(value, unit, valued_at=None, **extra):
    obj = {"value": None if value is None else float(value), "unit": unit}
    if valued_at is not None:
        obj["valued_at"] = valued_at
    obj.update(extra)
    return obj


def count(n, unit="addresses"):
    return {"value": int(n), "unit": unit}


def rel(path):
    return str(path.relative_to(ROOT))


def csvrows(path):
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class StreamObject:
    """Parse every JSON member, releasing large top-level array rows immediately.

    This validates full JSON and gzip EOF, including arrays we do not retain.
    A row is never used if a later portion of its file is partial or unreadable.
    """
    def __init__(self, fh):
        self.fh, self.buf, self.pos, self.eof = fh, "", 0, False
        self.decoder = json.JSONDecoder()

    def more(self, size=65536):
        self.buf = self.buf[self.pos:]
        self.pos = 0
        chunk = self.fh.read(size)
        self.buf += chunk
        self.eof = not chunk

    def peek(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if self.eof:
                return ""
            self.more()

    def take(self, char):
        if self.peek() != char:
            raise ValueError(f"Expected {char!r} in timeline JSON")
        self.pos += 1

    def value(self):
        self.peek()
        read_size = 65536
        while True:
            try:
                v, end = self.decoder.raw_decode(self.buf, self.pos)
                # A number at a chunk boundary may still have more digits.
                if end == len(self.buf) and not self.eof:
                    self.more()
                    continue
                self.pos = end
                return v
            except json.JSONDecodeError:
                if self.eof:
                    raise
                # Some BTC transactions contain enormous input/output arrays.
                # Grow incomplete-value reads geometrically rather than
                # rescanning a multi-megabyte value every 64 KiB.
                self.more(read_size)
                read_size = min(read_size * 2, 16 * 1024 * 1024)

    def load(self, keep=False):
        out = {}
        self.take("{")
        if self.peek() != "}":
            while True:
                key = self.value()
                if not isinstance(key, str):
                    raise ValueError("Non-string JSON object key")
                self.take(":")
                if self.peek() == "[":
                    self.take("[")
                    vals = []
                    if self.peek() != "]":
                        while True:
                            v = self.value()
                            if keep and key == "txs":
                                if not isinstance(v, dict):
                                    raise ValueError("Non-object transaction row")
                                vals.append(v)
                            elif keep and key not in {"pool_logs", "daily_balance"}:
                                vals.append(v)
                            if self.peek() == "]":
                                break
                            self.take(",")
                    self.take("]")
                    if keep:
                        out[key] = vals
                    elif key == "txs":
                        out[key] = []
                else:
                    v = self.value()
                    if keep or key in {"chain", "address", "coverage", "fetched_at"}:
                        out[key] = v
                if self.peek() == "}":
                    break
                self.take(",")
        self.take("}")
        if self.peek():
            raise ValueError("Trailing data after timeline object")
        if not isinstance(out.get("coverage"), dict) or not isinstance(out.get("txs"), list):
            raise ValueError("Missing timeline coverage/txs")
        return out


def load_timeline(path, keep=False):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return StreamObject(fh).load(keep)


def assetof(chain, row):
    asset = row.get("asset", "")
    if asset == NATIVE.get(chain):
        return asset
    token = TOKENS.get((chain, asset.lower() if chain == "ETH" else asset))
    if token and str(row.get("decimals")) == str(token[1]):
        return token[0]
    return None


@lru_cache(maxsize=200000)
def quote(symbol, timestamp):
    value, valued, source = price.usd(symbol, timestamp)
    if value is None:
        return None
    # usd() chooses the observation; recover its raw provenance from the same row.
    for frequency in ("1h", "1d"):
        row = price._lookup_rows(symbol, frequency, timeof(timestamp))
        if row and row["valuation_time_utc"] == valued and row["source"] == source:
            return {"price": row["price_usd"], "valued_at": valued,
                    "source": source, "source_url": row["source_url"], "raw_ref": row["raw_ref"]}
    raise ValueError("usd() observation has no saved price provenance")


def valued(amount, symbol, timestamp):
    q = quote(symbol, timestamp)
    if not q:
        return number(None, "usd", timestamp, requested_at=timestamp,
                      unavailable_reason="No sufficiently fresh saved price")
    return number(amount * Decimal(q["price"]), "usd", q["valued_at"],
                  requested_at=timestamp, price_evidence=q)


def explorer(chain, tx):
    prefixes = {"ETH": "https://etherscan.io/tx/", "BTC": "https://mempool.space/tx/",
                "TRX": "https://tronscan.org/#/transaction/", "LTC": "https://litecoinspace.org/tx/"}
    return {"chain": chain.lower(), "hash": tx, "explorer_url": prefixes[chain] + tx}


@lru_cache(maxsize=10000)
def labels(chain, address):
    try:
        claims = lookup_label(chain, address)
    except FileNotFoundError:
        return []
    return [{k: r.get(k, "") for k in ("label", "class", "confidence", "source_url",
                                       "raw_ref", "valid_from", "valid_to")}
            for r in claims if r.get("class") != "scam_poisoning"]


def transfer(chain, address, row, listed_date, timeline_ref):
    timestamp = row.get("time_utc")
    t = timeof(timestamp)
    symbol = assetof(chain, row)
    amount = dec(row.get("amount"))
    if (not t or not symbol or amount is None or amount <= 0 or row.get("success") is False
            or row.get("is_transfer") is False or row.get("direction") not in {"in", "out"}):
        return None
    usd = valued(amount, symbol, iso(t))
    if usd["value"] is None or usd["value"] < 1:
        return None
    direction = row["direction"]
    counterparty = row.get("to" if direction == "out" else "from")
    # UTXO net debits do not assign a source's contribution to individual outputs.
    candidates = row.get("output_addresses" if direction == "out" else "input_addresses", [])
    if not candidates:
        candidates = row.get("counterparties", [])
    candidates = sorted(set(x for x in candidates if x != address))
    if chain in {"BTC", "LTC"}:
        counterparty = candidates[0] if len(candidates) == 1 else None
    if counterparty == address:
        return None
    start, noon, end = day_bounds(listed_date)
    obj = {"date": iso(t), "kind": "first_outflow" if direction == "out" else "inflow",
           "address_id": f"{chain.lower()}:{address}", "address": address,
           "direction": direction, "asset": symbol, "amount": number(amount, f"native:{symbol}"),
           "amount_exact": str(amount), "usd": usd,
           "tx": explorer(chain, row["hash"]), "raw_ref": row.get("raw_ref"),
           "timeline_ref": timeline_ref, "source_url": explorer(chain, row["hash"])["explorer_url"],
           "counterparty": counterparty, "counterparty_candidates": candidates[:5],
           "counterparty_count": count(len(candidates)),
           "counterparty_labels": [],
           "listed_date": listed_date, "after_T": t >= start,
           "publication_order": "after entire OFAC date" if t >= end else
                                "before OFAC date" if t < start else "same day; publication order unknown",
           "lag_days": number((t - noon).total_seconds() / 86400, "days"),
           "lag_days_interval": {"lower": number((t - end + dt.timedelta(seconds=1)).total_seconds() / 86400, "days"),
                                 "upper": number((t - start).total_seconds() / 86400, "days")},
           "classification_rule": "Exact native/token identity; positive successful transfer; saved-time USD >=1; no fake-token-symbol valuation"}
    if chain in {"BTC", "LTC"}:
        obj["amount_basis"] = "address net debit excluding allocated fee" if direction == "out" else "address net credit"
        obj["attribution_note"] = "No controller inference; mixed-input outputs cannot be apportioned; new-address change is unidentified."
    if row.get("kind") == "pool_withdrawal":
        obj["amount_basis"] = "full pool denomination, including relayer fee; not just beneficiary payment"
    return obj


def amounts_text(rows):
    return ", ".join(f"{float(Decimal(r['amount_exact'])):,.10g} {r['asset']}" for r in rows) or "unavailable"


def account(j, chain, address, listed_date, path, freeze_rows, tornado):
    """Reconcile each allowlisted asset before reconstructing its opening balance."""
    start, _, _ = day_bounds(listed_date)
    sums, at_T, refs = defaultdict(Decimal), defaultdict(Decimal), defaultdict(set)
    pool = j.get("tornado_pool") is True
    current = {assetof(chain, b): b for b in j.get("balance_now", [])
               if assetof(chain, b) and (not pool or assetof(chain, b) == NATIVE[chain])}
    txs = j.get("txs", [])
    missing_times = 0
    unknown = 0
    incoming_top, incoming_latest, outgoing, before = [], [], [], []
    in_count = out_count = 0
    native = NATIVE[chain]
    for row in txs:
        symbol = assetof(chain, row)
        if pool and symbol != native:
            symbol = None
        timestamp = timeof(row.get("time_utc"))
        if not timestamp:
            missing_times += 1
        if not symbol:
            unknown += 1
        fee = dec(row.get("fee", 0)) or Decimal(0)
        if row.get("fee_asset", native) == native:
            sums[native] -= fee
            if timestamp and timestamp < start:
                at_T[native] -= fee
        if symbol:
            amount = dec(row.get("amount"))
            if amount is not None and row.get("success") is not False:
                delta = amount if row.get("direction") == "in" else -amount if row.get("direction") == "out" else Decimal(0)
                sums[symbol] += delta
                if timestamp and timestamp < start:
                    at_T[symbol] += delta
                if row.get("raw_ref"):
                    refs[symbol].add(row["raw_ref"].split("#")[0])
        tr = transfer(chain, address, row, listed_date, rel(path))
        if tr:
            if tr["after_T"]:
                if tr["direction"] == "in":
                    in_count += 1
                    incoming_top.append(tr)
                    incoming_top.sort(key=lambda e: (-e["usd"]["value"], timeof(e["date"]), e["tx"]["hash"]))
                    del incoming_top[3:]
                    incoming_latest.append(tr)
                    incoming_latest.sort(key=lambda e: (timeof(e["date"]), e["tx"]["hash"]))
                    del incoming_latest[:-3]
                else:
                    out_count += 1
                    outgoing.append(tr)
                    outgoing.sort(key=lambda e: (timeof(e["date"]), e["tx"]["hash"]))
                    del outgoing[3:]
            elif tr["direction"] == "out":
                before.append(tr)
                before.sort(key=lambda e: (timeof(e["date"]), e["tx"]["hash"]))
                del before[:-3]
    # Issuer destruction may change supply without emitting a Transfer event.
    burn_adjustments = []
    for f in freeze_rows:
        if f["event"] not in BURN or not f.get("amount"):
            continue
        if any(t.get("hash") == f["tx_hash"] and t.get("direction") == "out"
               and assetof(chain, t) == f["token"] for t in txs):
            continue
        amount = dec(f["amount"])
        if amount is None:
            continue
        sums[f["token"]] -= amount
        if timeof(f["timestamp"]) < start:
            at_T[f["token"]] -= amount
        burn_adjustments.append({"raw_ref": f["raw_ref"], "tx": explorer(chain, f["tx_hash"]),
                                 "amount": number(amount, "native:" + f["token"])})
    observation = j.get("balance_observation", {})
    assets = []
    for symbol in sorted(set(sums) | set(current)):
        b = current.get(symbol)
        now = dec(b.get("amount")) if b else None
        decimals = int(b.get("decimals") or (18 if chain == "ETH" else 8 if chain in {"BTC", "LTC"} else 6)) if b else 18
        tolerance = Decimal(10) ** -decimals
        reconciles = now is not None and abs(sums[symbol] - now) <= tolerance
        full = j["coverage"].get("complete") is True
        if pool:
            full = j["coverage"].get("pool_events_complete") is True or j.get("log_coverage", {}).get("complete") is True
        historic = at_T[symbol] if full and reconciles and missing_times == 0 and at_T[symbol] >= 0 else None
        method = "complete transfer history, fees and separately evidenced burns; reconciles to current state"
        historic_refs = sorted(refs[symbol])
        observed_T = None
        if pool and symbol == "ETH":
            checkpoint = next((c for c in tornado.get("legal_checkpoint_balances", [])
                               if c.get("id") == "designation" and c.get("target_time_utc") == iso(start)), {})
            direct = next((p for p in checkpoint.get("pools", []) if p["address"] == address), None)
            if direct:
                historic = Decimal(direct["amount_raw"]) / Decimal(10) ** 18
                historic_refs = [direct["raw_ref"], checkpoint["block_raw_ref"]]
                observed_T = checkpoint["observed_time_utc"]
                method = "independent archive eth_getBalance at final block before T; results/tornado.json checkpoint"
        observed = (b or {}).get("as_of") or (b or {}).get("reported_at") or observation.get("time_utc") or j.get("balance_checked_at") or j.get("fetched_at")
        assets.append({"asset": symbol, "chain": chain.lower(),
                       "designation": {"amount": number(historic, "native:" + symbol),
                                       "amount_exact": str(historic) if historic is not None else None,
                                       "checkpoint": iso(start), "observed_at": observed_T,
                                       "usd": valued(historic, symbol, iso(start)) if historic is not None else number(None, "usd", iso(start)),
                                       "method": method if historic is not None else "unavailable: incomplete history, undated rows, or failed reconciliation",
                                       "raw_refs": historic_refs},
                       "today": {"amount": number(now, "native:" + symbol), "amount_exact": str(now) if now is not None else None,
                                 "observed_at": observed, "usd": valued(now, symbol, observed) if now is not None and observed else number(None, "usd", observed),
                                 "raw_ref": (b or {}).get("raw_ref"), "source_url": (b or {}).get("source"),
                                 "rpc_response_id": (b or {}).get("rpc_response_id")},
                       "reconciliation": {"matches": reconciles, "history_implied_exact": str(sums[symbol]),
                                          "observed_exact": str(now) if now is not None else None,
                                          "difference_exact": str(sums[symbol] - now) if now is not None else None}})
    metric = {"id": f"{chain.lower()}:{address}", "listed_date": listed_date, "timeline_ref": rel(path), "raw_ref": rel(path),
              "coverage_complete": j["coverage"].get("complete", False),
              "scope_complete": full if assets else False,
              "checked_through": j["coverage"].get("checked_through_time") or j["coverage"].get("to_time"),
              "fetched_at": j.get("fetched_at"), "assets": assets,
              "undated_records": count(missing_times, "events"), "unvalued_identity_records": count(unknown, "events"),
              "burn_adjustments": burn_adjustments,
              "observed_nondust_post_T_inflows": count(in_count, "events"),
              "observed_nondust_post_T_outflows": count(out_count, "events")}
    incoming = list({(e["tx"]["hash"], e["asset"], e["date"], e["amount_exact"]): e
                     for e in incoming_top + incoming_latest}.values())
    return metric, incoming, outgoing, before


def total_balance(metrics, when, date=None, as_of=None):
    rows = [(m, a) for m in metrics if date is None or m["listed_date"] == date for a in m["assets"]]
    known = [(m, a) for m, a in rows if a[when]["usd"]["value"] is not None]
    requested = sorted({a[when]["usd"].get("requested_at", a[when]["usd"]["valued_at"]) for m, a in known})
    actual = sorted({a[when]["usd"]["valued_at"] for m, a in known})
    # No observations -> null, never zero; zero is valid only from an observation.
    amount = sum((Decimal(str(a[when]["usd"]["value"])) for m, a in known), Decimal(0)) if known else None
    stamp = actual[-1] if actual else iso(day_bounds(date)[0]) if date else as_of or "1970-01-01T00:00:00Z"
    return number(amount, "usd", stamp,
                  valuation_times=actual, requested_times=requested, priced_assets=count(len(known), "asset_observations"),
                  unavailable_assets=count(len(rows) - len(known), "asset_observations"),
                  partial=len(known) != len(rows) or not rows,
                  valuation_basis="Sum of per-asset valuations; valued_at is the latest quote timestamp, not a common observation time; see valuation_times and address_metrics",
                  covers="Native coin plus exact-contract USDT, USDC and DAI where observed; other tokens excluded")


def freeze_event(f, address_row):
    start, noon, end = day_bounds(address_row["first_listed_date"])
    t = timeof(f["timestamp"])
    kind = "freeze" if f["event"] in ADD else "burn" if f["event"] in BURN else "other"
    amount = dec(f.get("balance_at_freeze")) if kind == "freeze" else dec(f.get("amount")) if kind == "burn" else None
    obj = {"date": iso(t), "kind": kind,
           "label": f"{f['token']} {f['event']} for {f['address_normalized']}",
           "issuer": "circle" if f["token"] == "USDC" else "tether",
           "asset": f["token"], "address_id": f"{f['chain'].lower()}:{f['address_normalized']}",
           "amount": number(amount, "native:" + f["token"]),
           "usd": valued(amount, f["token"], iso(t)) if amount is not None else number(None, "usd", iso(t)),
           "amount_note": "archive balance at end of freeze block" if kind == "freeze" and amount is not None else
                          "burn-time token amount; not an earlier freeze balance" if kind == "burn" else
                          "amount unavailable; blacklist logs do not state frozen balance",
           "lag_hours": number((t - noon).total_seconds() / 3600, "hours"),
           "lag_hours_interval": {"lower": number((t - end + dt.timedelta(seconds=1)).total_seconds() / 3600, "hours"),
                                  "upper": number((t - start).total_seconds() / 3600, "hours")},
           "publication_order": "before entire OFAC date" if t < start else
                                "after entire OFAC date" if t >= end else "same day; publication order unknown",
           "listed_date": address_row["first_listed_date"], "tx": explorer(f["chain"], f["tx_hash"]),
           "raw_ref": f["raw_ref"], "balance_raw_ref": f.get("balance_raw_ref") or None,
           "source_url": f["source_url"], "event": f["event"]}
    return obj


def event_from_transfer(tr, first=False):
    e = dict(tr)
    e["kind"] = "first_outflow" if first else "inflow" if tr["direction"] == "in" else "other"
    labels_text = "; ".join(sorted({x["label"] for x in tr["counterparty_labels"]}))
    e["label"] = (("First observed non-dust outflow after this address's T" if first else
                   "Observed non-dust inflow" if tr["direction"] == "in" else "Observed pre-T outflow")
                  + f": {tr['amount_exact']} {tr['asset']}" + (f"; destination label: {labels_text}" if labels_text else ""))
    return e


def finding(id_, sentence, metric, examples, confidence, raw_refs=()):
    examples = list({(e["tx"]["chain"], e["tx"]["hash"]): e for e in examples}.values())
    return {"id": id_, "sentence": sentence, "number": metric,
            "example_txs": [{**e["tx"], "date": e["date"], "raw_ref": e.get("raw_ref"),
                             "amount": e.get("amount"), "usd": e.get("usd")} for e in examples[:3]],
            "confidence": confidence, "raw_refs": list(raw_refs), "script": SCRIPT}


def make_case(ref, ledger, addresses, metrics, incoming, outgoing, before, all_freezes, tornado, snapshot):
    id_ = ref["case_id"]
    names = ref["name"].split("; ")
    entity_rows = [r for r in ledger if r["sdn_name"] in names]
    keys = {(chain, r["address_normalized"]) for r in entity_rows for chain in (r.get("chains") or r["chain"]).split(";")}
    addr_rows = {k: addresses[k] for k in sorted(keys) if k in addresses}
    freezes = sorted([freeze_event(f, addr_rows[(f["chain"], f["address_normalized"])])
                      for f in all_freezes if (f["chain"], f["address_normalized"]) in addr_rows],
                     key=lambda e: (e["date"], e["tx"]["hash"], e["address_id"]))
    additions = [f for f in freezes if f["event"] in ADD]
    early_blacklists = [f for f in additions if f["publication_order"] == "before entire OFAC date"]
    earlier_cleared = [f for f in freezes if f["event"] in REMOVE
                       and f["address_id"] in {e["address_id"] for e in early_blacklists}
                       and f["publication_order"] == "before entire OFAC date"]
    incoming.sort(key=lambda e: (timeof(e["date"]), e["tx"]["hash"], e["address_id"]))
    outgoing.sort(key=lambda e: (timeof(e["date"]), e["tx"]["hash"], e["address_id"]))
    before.sort(key=lambda e: (timeof(e["date"]), e["tx"]["hash"]))
    largest = sorted(incoming, key=lambda e: (-e["usd"]["value"], timeof(e["date"]), e["tx"]["hash"]))[:3]
    # Resolve labels only for retained evidence, rather than opening SQLite for
    # hundreds of thousands of pool participants that will not be published.
    for e in incoming + outgoing + before:
        if e["counterparty"]:
            e["counterparty_labels"] = [r for r in labels(e["tx"]["chain"].upper(), e["counterparty"]) if
                (not r.get("valid_from") or e["date"][:10] >= r["valid_from"][:10]) and
                (not r.get("valid_to") or e["date"][:10] < r["valid_to"][:10])]
    today = total_balance(metrics, "today", as_of=snapshot)
    first = outgoing[0] if outgoing else None
    scoped = "four classic Ethereum pools" if id_ == "tornado-cash" else "OFAC-listed addresses in this case with readable timelines"
    one_liner = {
        "tornado-cash": "The protocol's contracts continued processing withdrawals; Treasury removed the designation in March 2025.",
        "lazarus-ronin": "The address-addition dates differ from the group's original designation; the listed Ethereum addresses kept moving funds.",
        "garantex-grinex": "The original identifiers and the addresses added in 2025 are different cohorts; their clocks must stay separate.",
        "hamas-tron-aljebouri": "One listed Tron address was already on Tether's blacklist long before its OFAC address listing.",
        "sinbad": "A listed Bitcoin address was spent after the designation; the transaction does not establish who authorized it.",
        "suex": "Issuer blacklist events and native-coin transactions have different capabilities and timelines.",
        "samsam-first-addresses": "Treasury's first two published Bitcoin identifiers still have later receipts; small receipts require a dust check.",
        "cryptex-pm2btc": "The four listed identifiers provide a narrow view of the exchange; sparse activity is not its total business volume.",
    }[id_]
    if id_ == "garantex-grinex" and early_blacklists and earlier_cleared:
        one_liner = "A later-listed address was blacklisted by Tether, unblacklisted, and then listed by OFAC."
    events = [{"date": ref["designation_date"], "kind": "designation",
               "label": ref["action_type"].replace("_", " ") + "; T uses each address's first publication date",
               "source_url": ref["treasury_press_release_url"] or ref["recent_actions_url"],
               "raw_ref": ref["raw_ref"], "amount": total_balance(metrics, "designation", ref["designation_date"])}]
    if first:
        events.append(event_from_transfer(first, True))
    if additions:
        events.append(additions[0])
        if id_ == "hamas-tron-aljebouri" and additions[-1]["date"] != additions[0]["date"]:
            events.append(additions[-1])
        if id_ == "garantex-grinex" and early_blacklists and earlier_cleared:
            events.extend([early_blacklists[0], earlier_cleared[0]])
    if largest and id_ != "garantex-grinex":
        e = event_from_transfer(largest[0]); e["label"] = "Largest observed post-T inflow by USD at transfer time: " + e["label"]
        events.append(e)
    if incoming and (not largest or incoming[-1]["tx"]["hash"] != largest[0]["tx"]["hash"]):
        e = event_from_transfer(incoming[-1]); e["label"] = "Latest observed post-T non-dust receipt: " + e["label"]
        events.append(e)
    if before and len(events) < 6 and id_ != "garantex-grinex":
        events.append(event_from_transfer(before[-1]))
    for action in json.loads(ref["related_actions"]):
        if id_ == "tornado-cash" and action["action_type"] in {"delisting", "removal_of_original_entry_and_immediate_redesignation"}:
            events.append({"date": action["date"], "kind": "delisting" if action["action_type"] == "delisting" else "designation",
                           "label": action["action_type"].replace("_", " "),
                           "source_url": action["treasury_press_release_url"], "raw_ref": action["raw_ref"]})
        elif id_ == "garantex-grinex" and action["name"] == ref["name"]:
            events.append({"date": action["date"], "kind": "designation", "label": "Additional designation and new address identifiers; not the 2022 cohort",
                           "source_url": action["treasury_press_release_url"], "raw_ref": action["raw_ref"]})
    observed = sorted({a["today"]["observed_at"] for m in metrics for a in m["assets"] if a["today"]["observed_at"]})
    latest = observed[-1] if observed else snapshot
    if not first and len(events) < 7:
        events.append({"date": latest, "kind": "other", "label": "No priced outflow >= USD 1 found after T within the checked scope; unavailable histories are not inactivity", "source_url": ref["recent_actions_url"]})
    if not additions and len(events) < 7:
        events.append({"date": latest, "kind": "other", "label": "No matching issuer blacklist event in the checked ETH USDT/USDC and TRX USDT table; an issuer token blacklist does not immobilize native coin", "raw_ref": "data/freezes.csv"})
    events.append({"date": latest, "kind": "other", "label": "Latest saved balances; observation dates vary by address and asset", "amount": today,
                   "raw_ref": sorted({a["today"]["raw_ref"] for m in metrics for a in m["assets"] if a["today"]["raw_ref"]})})
    if len(events) < 5:
        events.append({"date": latest, "kind": "other",
                       "label": "Designation balance unavailable in this saved-data scope; missing timelines are not zero balances",
                       "amount": total_balance(metrics, "designation", ref["designation_date"]),
                       "raw_ref": ["data/addresses.csv", "data/ledger.csv"]})
    # Keep a readable eight-event timeline; all omitted detail remains below.
    if len(events) > 8:
        latest_receipt = next((e for e in events if e["label"].startswith("Latest observed post-T")), None)
        if latest_receipt:
            events.remove(latest_receipt)
    for e in events:
        if len(e["date"]) == 10:
            e["date_precision"] = "OFAC action date only; intraday publication unknown; sorted at T checkpoint"
    events.sort(key=lambda e: (day_bounds(e["date"])[0] if len(e["date"]) == 10 else timeof(e["date"]), e["kind"]))
    findings = []
    confidence = "High confidence in the cited saved on-chain records; coverage is provisional. Date-level OFAC timing cannot establish same-day publication order. USD uses the stated saved observation, with stablecoin market-price assumptions inherited from the price source."
    if id_ == "hamas-tron-aljebouri" and additions:
        early = [f for f in additions if f["publication_order"] == "before entire OFAC date"]
        if early:
            f = early[0]
            days = -f["lag_hours"]["value"] / 24
            findings.append(finding(id_ + "-early-freeze", f"A Tron address later listed under {ref['name']} was blacklisted by Tether {days:,.2f} days before the noon-ET listing-date proxy.",
                                    number(days, "days"), [f] + additions[-2:],
                                    confidence + " The full lag interval is stored in the freeze event. Frozen amount is unknown; current balance is not substituted."))
    elif id_ == "garantex-grinex":
        early = early_blacklists
        if early:
            n = len({f["address_id"] for f in early})
            context_events = [f for f in freezes if f["address_id"] in {e["address_id"] for e in early} and f not in early]
            noun = "address had an issuer blacklist event" if n == 1 else "addresses had issuer blacklist events"
            sentence = f"{n} later-listed GARANTEX EUROPE OU {noun} before the entire date OFAC first published the identifier."
            if earlier_cleared:
                sentence += f" The affected address was also unblacklisted on {earlier_cleared[0]['date'][:10]}, before its {earlier_cleared[0]['listed_date']} OFAC listing."
            findings.append(finding(id_ + "-earlier-blacklist", sentence,
                                    count(n), early[:3] + context_events[:2], confidence + " These are later address additions, not the initial 2022 cohort. Other examples show subsequent issuer events for the same address, not additional early-blacklisted addresses. Earlier blacklisting does not imply continuously frozen status; removals remain in the timeline. Cause and frozen amount are unknown."))
    elif id_ == "tornado-cash":
        native_now = sum((Decimal(a["today"]["amount_exact"]) for m in metrics for a in m["assets"] if a["asset"] == "ETH" and a["today"]["amount_exact"] is not None), Decimal(0))
        findings.append(finding(id_ + "-still-active", f"The four classic ETH pools held {native_now:,.1f} ETH at their latest saved balance blocks; post-delisting use is reported separately from the sanctions period.",
                                number(native_now, "native:ETH"), incoming[-3:], confidence + " Pools are contracts, not wallets. This is a balance stock, not unique funds or gross flow."))
    elif id_ == "sinbad" and first:
        findings.append(finding(id_ + "-later-spend", f"A listed SINBAD Bitcoin address had a {first['amount_exact']} BTC net debit excluding allocated fee on {first['date'][:10]}, after its address listing.",
                                first["amount"], [first] + before[-2:],
                                confidence + " The designation accompanied a disruption/seizure; the spender and output ownership are unknown. Other examples are explicitly pre-T context, not additional post-T spends."))
    elif id_ == "samsam-first-addresses" and incoming:
        latest_in = incoming[-1]
        days = (timeof(latest_in["date"]) - day_bounds(latest_in["listed_date"])[0]).total_seconds() / 86400
        findings.append(finding(id_ + "-later-receipt", f"An address published in Treasury's first Bitcoin-identifier action received a non-dust net credit {days:,.2f} days after T; receipt purpose is unknown.",
                                number(days, "days"), [latest_in] + largest[:2],
                                confidence + " This is an address receipt; it does not establish a ransomware payment, victim identity, donation or compliance violation."))
    elif id_ == "lazarus-ronin" and first:
        findings.append(finding(id_ + "-first-outflow", f"The first observed non-dust outflow after one of these address-specific listings was {first['amount_exact']} {first['asset']} on {first['date']}.",
                                first["amount"], outgoing[:3], confidence + " Later address additions have later T values. The cited transactions are address activity, not new identity attribution."))
    return {"id": id_, "name": ref["name"], "program": ref["program"],
            "designated": ref["designation_date"], "press_release_url": ref["treasury_press_release_url"] or None,
            "chains": sorted({k[0].lower() for k in addr_rows}), "one_liner": one_liner,
            "addresses": [f"{c.lower()}:{a}" for c, a in sorted(addr_rows)],
            "events": events, "today": {"balance_usd": today,
                "status_sentence": f"Latest saved observations for {scoped}; this is not an atomic live balance or the full entity's holdings.",
                "covers": scoped + "; native coin and allowlisted stablecoins; no same-string activity on unlisted chains",
                "observation_times": observed},
            "provisional": True, "source_url": ref["source_url"], "raw_ref": ref["raw_ref"],
            "scope": {"ledger_addresses": count(len(addr_rows)), "analysed_addresses": count(len(metrics)),
                      "balance_and_flow_address_ids": [m["id"] for m in metrics],
                      "freeze_scope": "all listed chain-address pairs for this case, including addresses outside the flow/balance subset",
                      "timeline_omissions": [f"{c.lower()}:{a}" for c, a in addr_rows if f"{c.lower()}:{a}" not in {m["id"] for m in metrics}],
                      "note": "Tornado flow/balance scope is four classic native-ETH pools; blacklist scope is the full listed set." if id_ == "tornado-cash" else "Listed identifiers only; not a vendor entity cluster."},
            "designation_balances": [{"date": date, "balance_usd": total_balance(metrics, "designation", date)} for date in sorted({m["listed_date"] for m in metrics})],
            "address_metrics": metrics, "first_outflow": first, "largest_post_T_inflows": largest,
            "latest_post_T_inflow": incoming[-1] if incoming else None,
            "last_pre_T_outflows": before[-3:], "issuer_events": freezes,
            "issuer_summary": {"blacklist_events": count(len(additions), "events"),
                               "blacklisted_addresses": count(len({f["address_id"] for f in additions})),
                               "frozen_amount_unavailable_events": count(sum(f["amount"]["value"] is None for f in additions), "events")},
            "findings": findings, "confidence": confidence, "context": ref["notes"],
            "legal_actions": json.loads(ref["related_actions"])}


def build():
    ledger = csvrows(ROOT / "data/ledger.csv")
    addr_list = csvrows(ROOT / "data/addresses.csv")
    addresses = {(r["chain"].upper(), r["address_normalized"]): r for r in addr_list}
    references = {r["case_id"]: r for r in csvrows(ROOT / "data/reference/cases.csv")}
    freezes = csvrows(ROOT / "data/freezes.csv") if (ROOT / "data/freezes.csv").exists() else []
    tornado = json.loads((ROOT / "results/tornado.json").read_text()) if (ROOT / "results/tornado.json").exists() else {}
    selected_keys = {}
    for id_ in SELECTION:
        names = references[id_]["name"].split("; ")
        keys = {(c, r["address_normalized"]) for r in ledger if r["sdn_name"] in names
                for c in (r.get("chains") or r["chain"]).split(";")}
        selected_keys[id_] = {k for k in keys if k in addresses and (id_ != "tornado-cash" or k[1] in CLASSIC)}
    selected_union = set().union(*selected_keys.values())
    # Reuse a full previous syntax/integrity audit only for identical bytes.
    # Selected case histories are always parsed and analysed again.
    previous = {}
    if OUT.is_file():
        try:
            previous = {e["id"]: e for e in json.loads(OUT.read_text()).get("timeline_inventory", [])}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    frozen = defaultdict(list)
    for f in freezes:
        frozen[(f["chain"], f["address_normalized"])].append(f)
    inventory, analysed, by_chain, invalid, changed = [], {}, defaultdict(Counter), [], []
    latest_fetched = []
    last_chain = None
    for key, row in sorted(addresses.items()):
        chain, address = key
        if chain != last_chain:
            print(f"Scanning {chain} timelines ({len(inventory)} ledger files checked so far)", file=sys.stderr, flush=True)
            last_chain = chain
        base = ROOT / "data/timelines" / chain.lower() / address
        path = next((Path(str(base) + suffix) for suffix in (".json.gz", ".json") if Path(str(base) + suffix).is_file()), None)
        by_chain[chain]["ledger"] += 1
        if not path:
            by_chain[chain]["missing"] += 1
            continue
        by_chain[chain]["present"] += 1
        stat = path.stat()
        entry = {"id": f"{chain.lower()}:{address}", "path": rel(path), "sha256": sha(path)}
        try:
            old = previous.get(entry["id"], {})
            if (key not in selected_union and old.get("status") == "readable"
                    and old.get("sha256") == entry["sha256"] and "coverage_complete" in old
                    and old.get("path") == entry["path"]):
                j = {"chain": chain.lower(), "address": address,
                     "coverage": {"complete": old["coverage_complete"]}, "fetched_at": old.get("fetched_at")}
            else:
                j = load_timeline(path, key in selected_union)
            if str(j.get("chain", "")).upper() != chain or j.get("address") != address:
                raise ValueError("Timeline chain/address disagrees with ledger pair")
            if path.stat().st_mtime_ns != stat.st_mtime_ns or path.stat().st_size != stat.st_size:
                changed.append(rel(path))
                entry["status"] = "changed_during_read"
            else:
                if key in selected_union and chain in NATIVE:
                    analysed[key] = account(j, chain, address, row["first_listed_date"], path, frozen[key], tornado)
                entry["status"] = "readable"
                entry["coverage_complete"] = j["coverage"].get("complete") is True
                entry["fetched_at"] = j.get("fetched_at")
                by_chain[chain]["readable"] += 1
                by_chain[chain]["complete"] += j["coverage"].get("complete") is True
                if j.get("fetched_at"):
                    latest_fetched.append(j["fetched_at"])
        except (OSError, EOFError, ValueError, TypeError, KeyError, InvalidOperation) as exc:
            entry["status"] = "unreadable_or_partial"
            invalid.append({"path": rel(path), "reason": str(exc)[:200]})
            by_chain[chain]["unreadable"] += 1
        inventory.append(entry)
    snapshot = iso(max((timeof(s) for s in latest_fetched if timeof(s)), default=dt.datetime(1970, 1, 1, tzinfo=UTC)))
    cases = []
    for id_ in SELECTION:
        metrics, ins, outs, pres = [], [], [], []
        for key in sorted(selected_keys[id_]):
            if key in analysed:
                m, i, o, p = analysed[key]
                metrics.append(m); ins.extend(i); outs.extend(o); pres.extend(p)
        cases.append(make_case(references[id_], ledger, addresses, metrics, ins, outs, pres, freezes, tornado, snapshot))
    deps = ["data/addresses.csv", "data/ledger.csv", "data/actions.csv", "data/freezes.csv",
            "data/reference/cases.csv", "scripts/prices/price.py", "scripts/labels/lookup.py",
            "scripts/labels/policy.py", "data/labels/labels.sqlite", "results/tornado.json"]
    deps += sorted(rel(p) for p in (ROOT / "data/prices").glob("*.csv.gz"))
    manifest = [{"path": p, "sha256": sha(ROOT / p)} for p in deps if (ROOT / p).is_file()]
    readable = sum(c["readable"] for c in by_chain.values())
    temporary = list((ROOT / "data/timelines").rglob("*.tmp*")) + list((ROOT / "data/timelines").rglob("*.part"))
    result = {"schema_version": 1, "script": SCRIPT, "provisional": True,
              "evidence_last_fetched_utc": snapshot, "timeline_count": readable,
              "timeline_count_unit": "addresses (listed chain-address pairs with readable timelines)",
              "coverage": {"ledger_addresses": count(len(addresses)), "ledger_address_entity_rows": count(len(ledger), "address_entity_pairs"),
                           "timelines_present": count(len(inventory)), "readable_timelines": count(readable),
                           "missing_timelines": count(len(addresses) - len(inventory)),
                           "unreadable_or_partial": count(len(invalid)), "changed_during_read": count(len(changed)),
                           "temporary_files_ignored": count(len(temporary), "files"),
                           "by_chain": [{"chain": c.lower(), "raw_ref": "data/addresses.csv", **{k: count(v) for k, v in sorted(stats.items())}} for c, stats in sorted(by_chain.items())],
                           "unreadable_files": invalid, "changed_files": changed},
              "methods": ["T is the chain-address first-publication date at 00:00 America/New_York; lag uses noon ET with full-day uncertainty interval.",
                          "Every new/changed timeline present at inventory is parsed to EOF; identical previously audited bytes can reuse their SHA-256-matched syntax audit. Incomplete gzip/JSON and concurrent replacements are skipped and counted. Selected case files are always reanalysed; no fetched data is edited.",
                          "Balance-at-T reconstruction requires complete paged histories, exact-asset reconciliation to current state, and exact timestamps. Missing observations are null.",
                          "Four Tornado ETH pools use independent archive balances from the Tornado analysis, with their original block/time/raw references. Full listed set is used only for blacklist context.",
                          "Recognized assets are native BTC/ETH/TRX/LTC and exact-contract USDT/USDC/DAI. All other token identities are unvalued, never silently priced by symbol.",
                          "USD uses price.usd() at or before requested time, with the actual valuation timestamp and saved price raw reference. Today means each asset's latest saved state, not a live or atomic snapshot.",
                          "First outflow is earliest observed successful positive transfer >=USD1 after that address's T. Incomplete histories cannot establish the true first outflow; UTXO amounts are net debits excluding allocated fee, not attributed output values.",
                          "Largest inflows rank individual observed address net credits/asset transfers by USD at transfer time; they are not unique funds, verified payments or inferred sender identities.",
                          "Blacklist event does not freeze native BTC/ETH/TRX. Blank frozen balances remain unknown; no present-day substitution. Lag is address-specific, including later additions.",
                          "After T includes later delisting periods; Tornado post-2025-03-21 activity is not described as continued sanctioned use.",
                          "Different designation-date cohorts are opening stocks at different times, not additive entity holdings; the same funds can move between listed addresses.",
                          "Cases are selected for recognizability and saved trackable evidence, not a representative sample. Changes in behavior do not isolate a sanctions effect."],
              "input_manifest": manifest, "timeline_inventory": inventory,
              "cases": cases,
              "findings": [f for case in cases for f in case["findings"]],
              "site_export": "The cases member contains DATA_CONTRACT cases.json records; export that array to site/data/cases.json.",
              "coverage_append_note": "Case-specific coverage is documented here and in CASES.md.",
              "disclaimer": "Research, not legal or compliance advice. On-chain receipts and transfers do not establish legal violations. Destination labels are leads, not ownership proof."}
    for case in cases:
        case["timeline_count"] = readable
    editorial = ["hamas-tron-aljebouri", "garantex-grinex", "sinbad",
                 "samsam-first-addresses", "tornado-cash", "lazarus-ronin"]
    result["findings"].sort(key=lambda f: next((n for n, prefix in enumerate(editorial) if f["id"].startswith(prefix)), len(editorial)))
    return result


def usd_text(obj):
    if obj["value"] is None:
        return "USD unavailable"
    times = obj.get("valuation_times", [])
    timing = f"quote observations {times[0]} through {times[-1]}" if len(times) > 1 else f"valued at {obj['valued_at']}"
    return f"${obj['value']:,.2f} USD ({timing})" + ("; partial asset coverage" if obj.get("partial") else "")


def tx_text(e):
    t = e.get("tx", e)
    return f"[{t['hash']}]({t['explorer_url']})"


def render(result):
    c = result["coverage"]
    lines = ["# Eight famous cases — provisional", "",
             f"Saved evidence last fetched: {result['evidence_last_fetched_utc']}. **{result['timeline_count']:,} of {c['ledger_addresses']['value']:,} ledger chain-address pairs have readable timelines.** Acquisition is still running.", "",
             f"Eight editorial cases are not eight entities: the SamSam case groups two OFAC-named individuals. {c['missing_timelines']['value']} ledger pairs have no timeline, {c['unreadable_or_partial']['value']} files are unreadable/partial, and {c['changed_during_read']['value']} changed during reading. Counts include explicit coverage stubs; a readable file is not necessarily a complete history.", "",
             "Rebuild with `.venv/bin/python scripts/analysis/cases.py`. Verify with `.venv/bin/python scripts/analysis/cases.py --check`; run accounting/parser checks with `--self-test`. Everything runs offline. A changed input makes `--check` fail and requires a fresh rebuild; active fetches can legitimately invalidate the previous output.", "",
             "The result wrapper records provisional status, timeline counts, input hashes and coverage. Its `cases` array follows the site contract and can be exported directly. Detail is retained in each case's `address_metrics`, `issuer_events`, `largest_post_T_inflows` and `findings`.", "",
             "## Reading these timelines", ""]
    lines += ["- " + rule for rule in result["methods"]]
    lines += ["", result["disclaimer"], "", "## Candidate findings", ""]
    for f in result["findings"]:
        lines += [f"### {f['id']}", "", f["sentence"], "",
                  f"Number: {f['number']['value']:,.10g} **{f['number']['unit']}**" + (f"; valued at {f['number']['valued_at']}" if "valued_at" in f["number"] else "") + ".",
                  "", "Confidence: " + f["confidence"], ""]
        for e in f["example_txs"]:
            lines.append(f"- {e['date']}: {tx_text(e)}; `{e['raw_ref']}`.")
        lines.append("")
    for case in result["cases"]:
        lines += [f"## {case['name']}", "", case["one_liner"], "",
                  references_sentence(case), "",
                  f"[Treasury press release]({case['press_release_url']}) · [OFAC action]({case['source_url']}). " + case["context"], "",
                  f"Scope: {case['scope']['ledger_addresses']['value']} listed chain-address pairs; {case['scope']['analysed_addresses']['value']} analysed for balances/flows. {case['today']['covers']}.", ""]
        for e in case["events"]:
            line = f"- **{e['date']}** — {e['label']}."
            if e.get("amount") and e["amount"]["value"] is not None:
                if e["amount"]["unit"] == "usd":
                    line += " " + usd_text(e["amount"]) + "."
                elif e.get("usd"):
                    line += " " + usd_text(e["usd"]) + "."
            if e.get("tx"):
                line += " " + tx_text(e) + "."
            elif e.get("source_url"):
                line += f" [Source]({e['source_url']})."
            if e.get("raw_ref"):
                line += " Evidence: " + ("; ".join(f"`{p}`" for p in e["raw_ref"]) if isinstance(e["raw_ref"], list) else f"`{e['raw_ref']}`") + "."
            lines.append(line)
        lines += ["", "### Balances and first movement", ""]
        for group in case["designation_balances"]:
            lines.append(f"The cohort first listed on {group['date']} had a measured priced subtotal of {usd_text(group['balance_usd'])} at its T checkpoint. Unavailable assets are excluded from the subtotal, not set to zero.")
        lines += ["", "| Chain-address | Asset | Balance at its T | Balance at latest observation | Evidence / limits |",
                  "|---|---|---|---|---|"]
        for m in case["address_metrics"]:
            for a in m["assets"]:
                old = a["designation"]
                new = a["today"]
                old_text = f"{old['amount_exact']} {a['asset']}; {usd_text(old['usd'])}" if old["amount_exact"] is not None else "Unavailable"
                new_text = f"{new['amount_exact']} {a['asset']}; {usd_text(new['usd'])}; observed {new['observed_at']}" if new["amount_exact"] is not None else "Unavailable"
                evidence = f"`{new['raw_ref']}`; {old['method']}. Timeline `{m['timeline_ref']}`."
                lines.append(f"| `{m['id']}` | {a['asset']} | {old_text} | {new_text} | {evidence} |")
        first = case["first_outflow"]
        lines.append("")
        if first:
            lo, hi = first["lag_days_interval"].values()
            lines += [f"First observed non-dust outflow: **{first['amount_exact']} {first['asset']}**, {usd_text(first['usd'])}, at {first['date']}; {tx_text(first)}. Lag from the noon-ET proxy: {first['lag_days']['value']:,.5f} days; publication-time uncertainty [{lo['value']:,.5f}, {hi['value']:,.5f}] days. {first['publication_order']}. `{first['raw_ref']}`.", ""]
            if first["counterparty_labels"]:
                for l in first["counterparty_labels"]:
                    lines.append(f"Destination label: {l['label']} ({l['class']}, {l['confidence']}); [label source]({l['source_url']}); `{l['raw_ref']}`. Historical validity may be unknown; label is a lead.")
            else:
                lines.append("No supported destination label for an attributable single counterparty. Multiple UTXO outputs remain unallocated.")
        else:
            lines.append("No priced outflow of at least USD 1 found after T within the checked scope. This does not establish inactivity outside coverage or for excluded/unpriced assets.")
        lines += ["", "### Issuer events", "",
                  f"Matched {case['issuer_summary']['blacklist_events']['value']} blacklist events across {case['issuer_summary']['blacklisted_addresses']['value']} listed chain-address pairs. Frozen amount is unavailable for {case['issuer_summary']['frozen_amount_unavailable_events']['value']} events. Native coin is outside an issuer token blacklist.", ""]
        for e in case["issuer_events"]:
            interval = e["lag_hours_interval"]
            amount_text = (f"{e['amount']['value']:,.10g} {e['asset']}; {usd_text(e['usd'])}. " if e['amount']['value'] is not None else "")
            lines.append(f"- {e['date']}: {e['label']}; lag {e['lag_hours']['value']:,.4f} hours, interval [{interval['lower']['value']:,.4f}, {interval['upper']['value']:,.4f}] hours; {e['publication_order']}. {amount_text}{e['amount_note']}. {tx_text(e)}; `{e['raw_ref']}`" + (f"; balance evidence `{e['balance_raw_ref']}`" if e.get('balance_raw_ref') else "") + ".")
        lines += ["", "### Largest receipts after each address's T", ""]
        if not case["largest_post_T_inflows"]:
            lines.append("No priced non-dust inflow observed in this scope; spam/unrecognized tokens are not dollar-valued.")
        for e in case["largest_post_T_inflows"]:
            lines.append(f"- {e['date']}: {e['amount_exact']} {e['asset']}; {usd_text(e['usd'])}; address `{e['address_id']}`; {tx_text(e)}; `{e['raw_ref']}`. {e['publication_order']}.")
        lines += ["", "Latest priced subtotal: " + usd_text(case["today"]["balance_usd"]) + ". " + case["today"]["status_sentence"],
                  "", "Confidence and limitations: " + case["confidence"], ""]
    lines += ["## Additional coverage limits", "",
              "Additional case coverage limits:", "",
              f"Cases snapshot: {result['timeline_count']} readable ledger chain-address timelines of {c['ledger_addresses']['value']}; {c['missing_timelines']['value']} missing, {c['unreadable_or_partial']['value']} unreadable/partial, {c['changed_during_read']['value']} replaced during read. Eight cases are provisional. Case balance/flow scopes are explicit; Tornado uses four native-ETH pools while issuer events match the full listed set. Unknown freeze amounts and failed historical reconciliations remain null. EVM/Tron/UTXO source limitations in docs/sources remain binding.", "",
               ""]
    return "\n".join(lines)


def references_sentence(case):
    first = case["first_outflow"]
    latest = case["latest_post_T_inflow"]
    issuer = [e for e in case["issuer_events"] if e["kind"] == "freeze"]
    sentences = []
    if first:
        sentences.append(f"Within the saved scope, the first priced outflow after an address's listing was {first['amount_exact']} {first['asset']} on {first['date'][:10]}.")
        if first["publication_order"].startswith("same day"):
            sentences.append("Its order relative to OFAC's intraday publication is unknown.")
    else:
        sentences.append("No priced non-dust outflow after T was found within the saved scope.")
    if issuer:
        sentences.append(f"The matched issuer history begins with a {issuer[0]['asset']} blacklist event on {issuer[0]['date'][:10]}.")
        if issuer[0]["publication_order"].startswith("before"):
            sentences.append("That event predates the whole day OFAC first published the affected address.")
        sentences.append("A blacklist record alone does not state how many tokens were immobilized.")
    if latest:
        sentences.append(f"A later non-dust receipt is recorded on {latest['date'][:10]}; its sender's purpose is unknown.")
    if case["id"] == "sinbad":
        sentences.append("The later Bitcoin debit does not identify the spender, and the coordinated disruption prevents a sanctions-only explanation.")
    if case["id"] == "cryptex-pm2btc":
        sentences.append("These four identifiers cannot stand in for an exchange-wide cluster, and fake-token receipts are excluded from dollar values.")
    if case["id"] == "tornado-cash":
        sentences.append("The four classic ETH contracts are separate from the full address set matched to issuer records. Use after the March 2025 removal is a distinct legal period.")
    return " ".join(sentences)


def self_test():
    good = '{"chain":"btc","address":"x","coverage":{"complete":true},"txs":[{"x":1},{"x":2}]}'
    assert len(StreamObject(io.StringIO(good)).load(True)["txs"]) == 2
    assert StreamObject(io.StringIO(good)).load(False)["txs"] == []
    for bad in [good[:-1], good[:-6], good + " garbage", good.replace("1}", "1,}")]:
        try:
            StreamObject(io.StringIO(bad)).load(True)
        except (ValueError, EOFError):
            pass
        else:
            raise AssertionError("Partial/invalid JSON accepted")
    # Large row crossing the input chunk boundary, and a scalar number boundary.
    big = json.dumps({"chain": "btc", "address": "x", "coverage": {}, "txs": [{"memo": "x" * 150000}]})
    assert len(StreamObject(io.StringIO(big)).load(True)["txs"][0]["memo"]) == 150000
    assert iso(day_bounds("2022-08-08")[0]) == "2022-08-08T04:00:00Z"
    assert iso(day_bounds("2018-11-28")[1]) == "2018-11-28T17:00:00Z"
    assert assetof("ETH", {"asset": "0xdead", "symbol": "USDT", "decimals": 6}) is None
    assert assetof("TRX", {"asset": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "decimals": 6}) == "USDT"
    assert number(None, "usd", "2020-01-01")["value"] is None
    compressed = gzip.compress(good.encode())
    try:
        with io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(compressed[:-4]))) as fh:
            StreamObject(fh).load(True)
    except (OSError, EOFError):
        pass
    else:
        raise AssertionError("Truncated gzip footer accepted")
    original_quote = globals()["quote"]
    original_labels = globals()["labels"]
    globals()["quote"] = lambda s, t: {"price": "1", "valued_at": t, "source": "fixture", "source_url": "fixture", "raw_ref": "fixture"}
    globals()["labels"] = lambda c, a: []
    try:
        def tx(time, direction, amount, fee="0", success=True, asset="ETH"):
            return {"time_utc": time, "direction": direction, "amount": amount, "fee": fee,
                    "success": success, "asset": asset, "hash": time + direction, "raw_ref": "fixture"}
        j = {"coverage": {"complete": True}, "txs": [
            tx("2020-01-01T12:00:00Z", "in", "10"),
            tx("2020-01-02T12:00:00Z", "out", "3", ".1"),
            tx("2020-01-03T12:00:00Z", "out", "50", ".2", False),
            tx("2020-01-03T14:00:00Z", "in", "1000000", asset="0xfake")],
             "balance_now": [{"asset": "ETH", "decimals": 18, "amount": "6.7", "as_of": "2020-01-04T00:00:00Z"}]}
        m, ins, outs, pres = account(j, "ETH", "0xtest", "2020-01-02", ROOT / "fixture", [], {})
        assert m["assets"][0]["designation"]["amount_exact"] == "10"
        assert m["assets"][0]["reconciliation"]["matches"]
        assert len(outs) == 1 and outs[0]["amount_exact"] == "3"
        assert m["unvalued_identity_records"]["value"] == 1
        j["coverage"]["complete"] = False
        m, *_ = account(j, "ETH", "0xtest", "2020-01-02", ROOT / "fixture", [], {})
        assert m["assets"][0]["designation"]["amount_exact"] is None
        j["coverage"]["complete"] = True
        j["balance_now"][0]["amount"] = "6.8"
        m, *_ = account(j, "ETH", "0xtest", "2020-01-02", ROOT / "fixture", [], {})
        assert m["assets"][0]["designation"]["amount_exact"] is None
        assert not m["assets"][0]["reconciliation"]["matches"]
        j["tornado_pool"] = True
        j["coverage"]["pool_events_complete"] = True
        j["balance_now"][0]["amount"] = "6.7"
        j["balance_now"].append({"asset": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", "decimals": 6, "amount": "0", "as_of": "2020-01-04T00:00:00Z"})
        m, *_ = account(j, "ETH", "0xtest", "2020-01-02", ROOT / "fixture", [], {})
        assert [a["asset"] for a in m["assets"]] == ["ETH"], "Native pool logs cannot establish unrelated-token opening balances"
        ref = next(r for r in csvrows(ROOT / "data/reference/cases.csv") if r["case_id"] == "sinbad")
        empty_case = make_case(ref, [], {}, [], [], [], [], [], {}, "2026-10-23T00:00:00Z")
        assert len(empty_case["events"]) == 5 and empty_case["today"]["balance_usd"]["value"] is None
    finally:
        globals()["quote"] = original_quote
        globals()["labels"] = original_labels
    print("PASS: full/partial JSON and gzip, ET dates, exact token identity, fees/failed transactions, reconciliation and unknown balances")


def validate(result):
    """Validate the publishable contract and every linked saved evidence file."""
    assert len(result["cases"]) == 8
    assert len({c["id"] for c in result["cases"]}) == 8
    required = {"id", "name", "program", "designated", "press_release_url", "chains", "one_liner", "addresses", "events", "today"}
    kinds = {"designation", "first_outflow", "freeze", "burn", "delisting", "inflow", "mixer", "exchange", "other"}
    for c in result["cases"]:
        assert required <= c.keys(), c["id"]
        assert 5 <= len(c["events"]) <= 8, (c["id"], len(c["events"]))
        for e in c["events"]:
            assert e["kind"] in kinds and timeof(e["date"]), e
    refs = set()
    def walk(value):
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            if value.get("unit") == "usd":
                assert timeof(value.get("valued_at")), value
            if {"hash", "explorer_url", "chain"} <= value.keys():
                assert re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", value["hash"]), value
                assert value["explorer_url"].startswith("https://"), value
            for key, item in value.items():
                if key in {"raw_ref", "raw_refs", "balance_raw_ref"} and item:
                    for ref in (item if isinstance(item, list) else [item]):
                        for part in ref.split(";"):
                            refs.add(part.strip().split("#")[0])
                walk(item)
    walk(result)
    missing = sorted(ref for ref in refs if not (ROOT / ref).is_file())
    if missing:
        raise ValueError("Missing published evidence files: " + ", ".join(missing[:10]))
    assert result["timeline_count"] == sum(e["status"] == "readable" for e in result["timeline_inventory"])
    return {"case_count": count(8, "cases"), "linked_saved_evidence_files": count(len(refs), "files"),
            "missing_evidence_files": count(0, "files"), "event_counts": {c["id"]: count(len(c["events"]), "events") for c in result["cases"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = build()
    from scripts.lib.fetch_status import apply_status, report_status
    result = apply_status(result, ROOT, "cases")
    result["validation"] = validate(result)
    serialized = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    markdown = report_status(render(result), result)
    if len(serialized.encode()) >= 5_000_000:
        raise ValueError("cases.json must remain under 5 MB")
    if args.check:
        differences = [str(p.relative_to(ROOT)) for p, text in [(OUT, serialized), (DOC, markdown)]
                       if not p.exists() or p.read_text() != text]
        if differences:
            print("CHECK FAILED: current saved evidence/output differs: " + ", ".join(differences), file=sys.stderr)
            return 1
        print(f"PASS: eight cases, {result['timeline_count']} readable ledger timelines; both outputs reproduced offline")
    else:
        for p, text in [(OUT, serialized), (DOC, markdown)]:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        print(f"Wrote eight cases; provisional={result['provisional']}; {result['timeline_count']} readable ledger timelines; {len(serialized.encode()):,} JSON bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
