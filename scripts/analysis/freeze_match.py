#!/usr/bin/env python3
"""Offline OFAC/issuer joins; rerun while timeline acquisition continues.

Only writes this analysis's three outputs. --check recomputes all three, reports any
input change, and never writes. Standard library only; execute with python -B -S.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo
import zlib

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.prices import price as prices

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
CONTRACTS = {("ETH", "USDT"): "0xdac17f958d2ee523a2206206994597c13d831ec7",
             ("ETH", "USDC"): "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
             ("TRX", "USDT"): "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"}
ADDS = {"AddedBlackList", "Blacklisted"}
REMOVES = {"RemovedBlackList", "UnBlacklisted"}
OUTPUTS = ("results/freeze_match.json", "data/derived/freeze_match.csv", "docs/analysis/FREEZE_MATCH.md")
ZERO = Decimal(0)
MICRO = Decimal("0.000001")


def iso(t):
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z") if t else None


def time(s):
    if not s:
        return None
    if isinstance(s, dt.datetime):
        return s.astimezone(UTC)
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def dec(v):
    try:
        n = Decimal(str(v))
        return n if n.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def num(v):
    return None if v is None else float(v)


def q(v, unit, valued_at=None):
    d = {"value": num(v) if isinstance(v, Decimal) else v, "unit": unit}
    if unit == "usd":
        d["valued_at"] = valued_at
    return d


def pct(a, b):
    return q(a / b if b else None, "share")


def quantile(values, p):
    x = sorted(values)
    if not x:
        return None
    i = (len(x) - 1) * p
    a = int(i)
    return x[a] + (x[min(a + 1, len(x) - 1)] - x[a]) * (i - a)


def normalize(a):
    return a.lower() if str(a).startswith("0x") else a


def integer(v, default=-1):
    try:
        return int(str(v), 16) if str(v).startswith("0x") else int(v)
    except (ValueError, TypeError):
        return default


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path):
    with (ROOT / path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class StreamJSON:
    """Stream top-level arrays without retaining pool/native/spam histories.

    json.raw_decode handles each array element; the final gzip read verifies its
    CRC/footer. Truncated and concurrently changed files are rejected as a unit.
    """
    def __init__(self, f):
        self.f, self.buf, self.pos, self.eof = f, "", 0, False
        self.decoder = json.JSONDecoder()

    def fill(self):
        self.buf = self.buf[self.pos:]
        self.pos = 0
        s = self.f.read(262144)
        self.buf += s
        self.eof = not s

    def peek(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos].isspace():
                self.pos += 1
            if self.pos < len(self.buf):
                return self.buf[self.pos]
            if self.eof:
                raise ValueError("incomplete JSON")
            self.fill()

    def eat(self, char):
        if self.peek() != char:
            raise ValueError("unexpected JSON delimiter")
        self.pos += 1

    def value(self):
        self.peek()
        while True:
            try:
                v, end = self.decoder.raw_decode(self.buf, self.pos)
                self.pos = end
                return v
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.fill()

    def document(self):
        meta, txs, total, txs_seen = {}, [], 0, False
        self.eat("{")
        while self.peek() != "}":
            key = self.value()
            self.eat(":")
            if self.peek() == "[":
                if key == "txs":
                    txs_seen = True
                vals = []
                self.eat("[")
                while self.peek() != "]":
                    v = self.value()
                    if key == "txs":
                        total += 1
                        if isinstance(v, dict) and normalize(v.get("asset", "")) in CONTRACTS.values():
                            txs.append(v)
                    elif key not in {"pool_logs", "daily_balance", "daily_balance_errors"}:
                        vals.append(v)
                    if self.peek() != "]":
                        self.eat(",")
                self.eat("]")
                if key not in {"txs", "pool_logs", "daily_balance", "daily_balance_errors"}:
                    meta[key] = vals
            else:
                meta[key] = self.value()
            if self.peek() != "}":
                self.eat(",")
        self.eat("}")
        if (self.buf[self.pos:] + self.f.read()).strip():
            raise ValueError("trailing JSON data")
        if not txs_seen:
            raise ValueError("missing transaction array in partial timeline")
        meta["txs"], meta["all_transaction_rows"] = txs, total
        return meta


def load_timeline(chain, address, manifest, skipped):
    base = ROOT / "data/timelines" / chain.lower()
    path = next((base / (address + suffix) for suffix in (".json.gz", ".json")
                 if (base / (address + suffix)).exists()), None)
    if path is None:
        return None, None
    rel = path.relative_to(ROOT).as_posix()
    try:
        before = path.stat()
        digest = sha(path)
        with (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz"
              else path.open(encoding="utf-8")) as f:
            d = StreamJSON(f).document()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("changed during read")
        if normalize(d.get("address")) != address or not isinstance(d.get("coverage"), dict):
            raise ValueError("timeline identity/schema mismatch")
        if str(d.get("chain", "")).upper() not in {chain, "TRON" if chain == "TRX" else chain}:
            raise ValueError("timeline chain mismatch")
        if not isinstance(d.get("balance_now", []), list):
            raise ValueError("malformed balance array")
        for tx in d["txs"]:
            if tx.get("time_utc"):
                time(tx["time_utc"])
        manifest[rel] = digest
        return d, rel
    except (OSError, EOFError, ValueError, TypeError, KeyError, zlib.error) as e:
        skipped.append({"path": rel, "reason": type(e).__name__ + ": " + str(e)[:160]})
        manifest[rel] = "unreadable_or_changed"
        return None, rel


def publication(s):
    if "T" in s or " " in s:
        p = time(s)
        return p, p, p, "exact ledger timestamp"
    day = dt.date.fromisoformat(s)
    return tuple(dt.datetime.combine(day, t, ET).astimezone(UTC)
                 for t in (dt.time(), dt.time(12), dt.time(23, 59, 59))) + ("date only; noon ET point",)


def event_order(f):
    return (integer(f.get("block")), integer(f.get("transaction_index")), integer(f.get("log_index")))


def state_at(events, ts=None):
    state = False
    for f in events:
        if ts is not None and time(f["timestamp"]) > ts:
            continue
        if f["event"] in ADDS:
            state = True
        elif f["event"] in REMOVES:
            state = False
    return state


def tx_evidence(chain, tx):
    h = tx.get("hash", tx.get("tx_hash"))
    return {"chain": chain, "hash": h,
            "explorer_url": ("https://etherscan.io/tx/" if chain == "ETH" else "https://tronscan.org/#/transaction/") + h,
            "raw_ref": tx.get("raw_ref"), "time_utc": tx.get("time_utc", tx.get("timestamp"))} if h else None


def valuation(token, amount, ts):
    p, at, source = prices.usd(token, ts)
    if p is None or amount is None:
        return {"value": None, "unit": "usd", "valued_at": at, "requested_at": iso(ts), "source": source}
    row = None
    for freq in ("1h", "1d"):
        r = prices._lookup_rows(token, freq, time(at))
        if r and r["valuation_time_utc"] == at and r["source"] == source:
            row = r
            break
    return {"value": float(amount * Decimal(str(p))), "unit": "usd", "valued_at": at,
            "requested_at": iso(ts), "price_usd": q(p, "usd", at), "source": source,
            "source_url": row.get("source_url") if row else None, "raw_ref": row.get("raw_ref") if row else None}


def token_analysis(d, chain, token, address, events, start, pub, end, first):
    """Use genuine contract transfers, accounting separately for issuer burns.

    No first-freeze balance is inferred from a later burn. State reconstruction
    requires genesis-complete token history, nonnegative arithmetic, and an
    independent latest balance agreement. Tron observations are not block pinned;
    a matching value is explicitly conditional, never labelled archive state.
    """
    result = {"timeline_token_complete": False, "ever_held": None, "held_at_T_or_after": None,
              "balance_at_T_native": None, "balance_at_first_freeze_native": None,
              "balance_at_freeze_method": "unknown", "reconciliation": "no timeline",
              "escape_native": None, "escape_lower_native": None, "escape_upper_native": None,
              "escape_usd": None, "escape_outgoing_events": None, "escape_examples": [],
              "holding_examples": [], "post_freeze_in_native": None, "post_freeze_in_source_cutoff_native": None,
              "post_freeze_in_source_cutoff_ge1usd_native": None, "notes": [], "burn_reconciliation": [],
              "post_freeze_in_source_cutoff_examples": [],
              "balance_at_T_end_native": None, "native_unit": "native:" + token,
              "freeze_balance_usd": None, "balance_at_T_usd": None,
              "balance_validation_difference_native": None, "token_transfer_rows": 0,
              "all_transaction_rows": 0, "exchange_scale": False,
              "balance_validation_raw_ref": None, "balance_at_freeze_raw_ref": None,
              "escape_complete": False}
    if not d:
        historical = dec(first.get("balance_at_freeze")) if first else None
        if historical is not None:
            ft = time(first["timestamp"])
            result["balance_at_first_freeze_native"] = num(historical)
            result["balance_at_freeze_method"] = first["balance_method"] + "; end-of-block, not exact pre-log state"
            result["balance_at_freeze_raw_ref"] = first["balance_raw_ref"]
            result["freeze_balance_usd"] = valuation(token, historical, ft)
            if historical > 0:
                result["ever_held"] = True
                if ft >= start:
                    result["held_at_T_or_after"] = True
        return result
    cov = d["coverage"]
    complete = ((cov.get("actions", {}).get("tokentx", {}).get("complete") is True and
                 cov.get("actions", {}).get("tokentx", {}).get("from_block") == 0)
                if chain == "ETH" else (cov.get("trc20_transfers_complete") is True and
                                        cov.get("history_start_requested_ms") == 0))
    pool = d.get("tornado_pool") is True
    if pool:
        complete = False
        result["notes"].append("Pool principal events omit full stablecoin Transfer history; no zero substituted.")
    result["timeline_token_complete"] = complete
    result["all_transaction_rows"] = d.get("all_transaction_rows", 0)
    result["exchange_scale"] = result["all_transaction_rows"] > 10000
    selected = [t for t in d["txs"] if normalize(t.get("asset", "")) == CONTRACTS[chain, token]
                and t.get("kind") not in {"pool_deposit", "pool_withdrawal"}
                and t.get("success") is not False]
    transfers = []
    for t in selected:
        amount, ts = dec(t.get("amount")), time(t.get("time_utc"))
        if amount is None or ts is None or amount < 0 or integer(t.get("decimals")) != 6:
            complete = result["timeline_token_complete"] = False
            result["notes"].append("Malformed genuine-token transfer; reconstruction disabled.")
            continue
        direction = t.get("direction")
        if direction not in {"in", "out", "self"}:
            complete = result["timeline_token_complete"] = False
            continue
        delta = amount if direction == "in" else -amount if direction == "out" else ZERO
        transfers.append((ts, delta, t))
    transfers.sort(key=lambda x: (x[0], integer(x[2].get("block")), integer(x[2].get("transactionIndex")), integer(x[2].get("logIndex"))))
    result["token_transfer_rows"] = len(transfers)
    incoming = [x for x in transfers if x[1] > 0]
    if incoming:
        result["ever_held"] = True
        result["holding_examples"] = [tx_evidence(chain, x[2]) for x in incoming[:3]]
    if any(x[0] >= start for x in incoming):
        result["held_at_T_or_after"] = True
    burns = [f for f in events if f["event"] == "DestroyedBlackFunds"]
    changes = list(transfers)
    for f in burns:
        # If an indexer emits an actual Transfer debit for this destruction,
        # subtract the destruction amount only once.
        debit = sum((-v for _, v, t in transfers if v < 0 and t.get("hash") == f["tx_hash"]
                     and t.get("to") in {"0x" + "0" * 40, "T9yD14Nj9j7xAB4dbGeiX9h8unkKHxuWwb"}), ZERO)
        amount = dec(f["amount"])
        if amount is not None:
            changes.append((time(f["timestamp"]), -(amount - debit), {"burn": True, **f}))
    changes.sort(key=lambda x: (x[0], integer(x[2].get("block")),
                               integer(x[2].get("logIndex", x[2].get("log_index")))))
    head = time(cov.get("checked_through_time", cov.get("to_time")))
    changes = [x for x in changes if head is None or x[0] <= head]
    running, min_balance = ZERO, ZERO
    for _, delta, _ in changes:
        running += delta
        min_balance = min(min_balance, running)
    balances = [b for b in d.get("balance_now", []) if normalize(b.get("asset", "")) == CONTRACTS[chain, token]]
    latest = balances[0] if balances else None
    observed = dec(latest.get("amount")) if latest else None
    diff = observed - running if observed is not None else None
    result["balance_validation_difference_native"] = num(diff)
    same_block = bool(latest and integer(latest.get("block")) == integer(cov.get("to_block")) and latest.get("block") is not None)
    matches = complete and min_balance >= 0 and diff == 0
    trusted = matches and (same_block or chain == "TRX")
    result["reconciliation"] = ("exact same-block match" if trusted and chain == "ETH" else
                                "match to non-atomic latest Tron observation" if trusted else
                                "incomplete token history" if not complete else
                                "negative reconstructed state" if min_balance < 0 else
                                "missing latest token balance" if observed is None else
                                "balance/history blocks differ" if diff == 0 else "balance mismatch")
    result["balance_validation_raw_ref"] = latest.get("raw_ref") if latest else None
    if observed and observed > 0:
        result["ever_held"] = True
        latest_time = time(latest.get("as_of")) or time(d.get("balance_observation", {}).get("time_utc")) or head
        if latest_time and latest_time >= start:
            result["held_at_T_or_after"] = True
    if trusted:
        at_T = sum((v for ts, v, _ in changes if ts < start), ZERO)
        at_end = sum((v for ts, v, _ in changes if ts <= end), ZERO)
        result["balance_at_T_native"], result["balance_at_T_end_native"] = num(at_T), num(at_end)
        result["balance_at_T_usd"] = valuation(token, at_T, start)
        if result["ever_held"] is None:
            result["ever_held"] = running > 0
        if result["held_at_T_or_after"] is None:
            result["held_at_T_or_after"] = at_T > 0
    elif complete and not incoming and observed == 0 and not pool:
        result["ever_held"] = False
        result["held_at_T_or_after"] = False
    if first:
        ftime = time(first["timestamp"])
        historical = dec(first.get("balance_at_freeze"))
        if historical is not None:
            result["balance_at_first_freeze_native"] = num(historical)
            result["balance_at_freeze_method"] = first["balance_method"] + "; end-of-block, not exact pre-log state"
            result["balance_at_freeze_raw_ref"] = first["balance_raw_ref"]
            if historical > 0:
                result["ever_held"] = True
                if ftime >= start:
                    result["held_at_T_or_after"] = True
        elif trusted and (head is None or ftime <= head):
            # Ethereum Transfer logs and blacklist logs share a global logIndex.
            # A missing index inside the freeze block or Tron timestamp tie is
            # ambiguous; do not silently order records by their hash.
            def before_freeze(x):
                ts, _, t = x
                if chain == "ETH" and integer(t.get("block")) >= 0:
                    b = integer(t["block"])
                    if b != integer(first["block"]):
                        return b < integer(first["block"])
                    idx = integer(t.get("logIndex", t.get("log_index")))
                    return None if idx < 0 else idx < integer(first["log_index"])
                return None if ts == ftime else ts < ftime
            relevant = [(x, before_freeze(x)) for x in changes]
            ambiguous = [x for x, before in relevant if before is None and x[1] != 0]
            if not ambiguous:
                value = sum((x[1] for x, before in relevant if before), ZERO)
                result["balance_at_first_freeze_native"] = num(value)
                result["balance_at_freeze_method"] = ("reconstructed genuine Transfer events minus non-Transfer issuer destructions; " + result["reconciliation"])
            else:
                result["notes"].append("Freeze-block/log or timestamp tie prevents exact pre-freeze balance.")
        frozen = dec(result["balance_at_first_freeze_native"])
        if frozen is not None:
            result["freeze_balance_usd"] = valuation(token, frozen, ftime)
        # Gross outgoing token volume; no inference of intent or external value.
        outgoing = [x for x in transfers if x[1] < 0]
        def escape(bound):
            return [x for x in outgoing if bound < x[0] < ftime]
        point, low, high = escape(pub), escape(end), escape(start)
        result["escape_native"] = num(sum((-x[1] for x in point), ZERO))
        result["escape_lower_native"] = num(sum((-x[1] for x in low), ZERO))
        result["escape_upper_native"] = num(sum((-x[1] for x in high), ZERO))
        result["escape_outgoing_events"] = len(point)
        values = [valuation(token, -x[1], x[0]) for x in point]
        result["escape_usd"] = q(sum(v["value"] for v in values) if all(v["value"] is not None for v in values) else None,
                                  "usd", "each outgoing transfer time; price observation at/before each transfer")
        result["escape_examples"] = [dict(tx_evidence(chain, x[2]), amount=q(-x[1], "native:" + token),
                                         valuation=valuation(token, -x[1], x[0])) for x in sorted(point, key=lambda x: x[1])[:3]]
        result["escape_complete"] = complete and head is not None and head >= ftime
        after = [x for x in incoming if x[0] > ftime and state_at(events, x[0])]
        cutoff = time("2026-10-08T00:00:00-04:00")
        source_after = [x for x in after if x[0] < cutoff]
        result["post_freeze_in_source_cutoff_examples"] = [dict(tx_evidence(chain, x[2]), amount=q(x[1], "native:" + token))
            for x in sorted(source_after, key=lambda x: -x[1])[:3]]
        result["post_freeze_in_native"] = num(sum((x[1] for x in after), ZERO))
        result["post_freeze_in_source_cutoff_native"] = num(sum((x[1] for x in source_after), ZERO))
        result["post_freeze_in_source_cutoff_ge1usd_native"] = num(sum((x[1] for x in source_after
            if (valuation(token, x[1], x[0])["value"] or 0) >= 1), ZERO))
    # Validate emitted destroyed amount against an independently reconstructed
    # pre-destruction balance, even if present-state reconciliation failed.
    for f in burns:
        ft = time(f["timestamp"])
        earlier = sum((v for ts, v, t in changes if ts < ft), ZERO)
        tied = [x for x in changes if x[0] == ft and not x[2].get("burn")]
        usable = complete and not tied and (head is not None and head >= ft)
        result["burn_reconciliation"].append({"tx_hash": f["tx_hash"], "testable": usable,
            "reconstructed_native": q(earlier if usable else None, "native:" + token),
            "emitted_native": q(dec(f["amount"]), "native:" + token),
            "match": (earlier == dec(f["amount"])) if usable else None,
            "raw_ref": f["raw_ref"], "source_url": f["source_url"]})
    return result


def make_row(a, ledger, chain, token, d, path, events):
    address = a["address_normalized"]
    start, pub, end, precision = publication(a["first_listed_date"])
    adds = [f for f in events if f["event"] in ADDS]
    removes = [f for f in events if f["event"] in REMOVES]
    burns = [f for f in events if f["event"] == "DestroyedBlackFunds"]
    first = adds[0] if adds else None
    ft = time(first["timestamp"]) if first else None
    relevant = [l for l in ledger if normalize(l["address_normalized"]) == address]
    names = sorted({l["sdn_name"] for l in relevant})
    tc = any(n == "TORNADO CASH" for n in names)
    valid = bool(re.fullmatch("0x[0-9a-f]{40}", address)) if chain == "ETH" else a.get("address_valid", "true") != "false"
    row = {"id": chain + ":" + address + ":" + token, "issuer": "tether" if token == "USDT" else "circle",
           "chain": chain, "token": token, "contract": CONTRACTS[chain, token], "address": address,
           "valid_token_address": valid, "listed_chains": a.get("listed_chains", chain),
           "listing_relation": a.get("listing_relation", "OFAC-listed chain"),
           "first_listed_date": a["first_listed_date"], "T_utc": iso(start), "T_pub_utc": iso(pub),
           "T_pub_earliest_utc": iso(start), "T_pub_latest_utc": iso(end), "T_pub_precision": precision,
           "year": start.astimezone(ET).year, "programs": sorted(set(a["programs"].split(";"))),
           "sdn_names": names, "sdn_uids": a.get("sdn_uids", ""), "tornado_cash": tc,
           "current_in_sdn": a.get("current_in_sdn") == "true", "delisted_date": a.get("delisted_date"),
           "timeline_ref": path, "timeline_readable": d is not None,
           "timeline_fetched_at": d.get("fetched_at") if d else None,
           "blacklisted_ever": bool(adds), "blacklisted_current": state_at(events),
           "blacklisted_at_T_pub": state_at(events, pub), "unblacklisted_ever": bool(removes),
           "first_blacklist_utc": iso(ft), "first_blacklist_tx": first["tx_hash"] if first else None,
           "first_blacklist_source_url": first["source_url"] if first else None,
           "first_unblacklist_utc": removes[0]["timestamp"] if removes else None,
           "lag_hours": (ft - pub).total_seconds() / 3600 if ft else None,
           "lag_lower_hours": (ft - end).total_seconds() / 3600 if ft else None,
           "lag_upper_hours": (ft - start).total_seconds() / 3600 if ft else None,
           "blacklist_event_count": len(adds), "unblacklist_event_count": len(removes),
           "burn_event_count": len(burns), "amount_burned_native": num(sum((dec(f["amount"]) for f in burns), ZERO)),
           "issuer_events": events, "source_url": sorted({l["listed_action_url"] for l in relevant if l["listed_action_url"]}),
           "raw_ref": sorted(set(filter(None, [a.get("raw_ref"), path] + [f["raw_ref"] for f in events] +
                                              [l.get("listed_raw_ref") for l in relevant])))}
    row.update(token_analysis(d, chain, token, address, events, start, pub, end, first))
    row["burn_valuations"] = [valuation(token, dec(f["amount"]), time(f["timestamp"])) for f in burns]
    row["amount_burned_usd"] = sum(v["value"] for v in row["burn_valuations"]) if all(v["value"] is not None for v in row["burn_valuations"]) else None
    return row


def summary(rows, **keys):
    adds = [r for r in rows if r["blacklisted_ever"]]
    holders = [r for r in rows if r["held_at_T_or_after"] is True]
    lag = [r["lag_hours"] for r in adds]
    frozen_known = [r for r in adds if r["balance_at_first_freeze_native"] is not None]
    usd = [r["freeze_balance_usd"]["value"] for r in frozen_known if r["freeze_balance_usd"] and r["freeze_balance_usd"]["value"] is not None]
    token = rows[0]["token"] if rows else keys.get("token", "USDT")
    escape_known = [r for r in adds if r.get("escape_native") is not None]
    escape_complete = [r for r in escape_known if r.get("escape_complete")]
    result = {**keys, "all_ofac_chain_addresses": q(len(rows), "addresses"),
       "valid_token_addresses": q(sum(r["valid_token_address"] for r in rows), "addresses"),
       "timeline_readable": q(sum(r["timeline_readable"] for r in rows), "addresses"),
       "complete_token_histories": q(sum(r["timeline_token_complete"] for r in rows), "addresses"),
       "observed_holders_at_T_or_after": q(len(holders), "addresses"),
       "holder_status_unknown": q(sum(r["held_at_T_or_after"] is None for r in rows), "addresses"),
       "blacklisted_ever": q(len(adds), "addresses"),
       "blacklisted_current": q(sum(r["blacklisted_current"] for r in rows), "addresses"),
       "unblacklisted_ever": q(sum(r["unblacklisted_ever"] for r in rows), "addresses"),
       "share_frozen_all_addresses": pct(len(adds), len(rows)),
       "share_currently_blacklisted_all_addresses": pct(sum(r["blacklisted_current"] for r in rows), len(rows)),
       "frozen_observed_holders": q(sum(r["blacklisted_ever"] for r in holders), "addresses"),
       "share_frozen_observed_holders": pct(sum(r["blacklisted_ever"] for r in holders), len(holders)),
       "currently_blacklisted_observed_holders": q(sum(r["blacklisted_current"] for r in holders), "addresses"),
       "share_currently_blacklisted_observed_holders": pct(sum(r["blacklisted_current"] for r in holders), len(holders)),
       "median_lag_hours": q(quantile(lag, .5), "hours"), "p90_lag_hours": q(quantile(lag, .9), "hours"),
       "median_lag_interval_lower_hours": q(quantile([r["lag_lower_hours"] for r in adds], .5), "hours"),
       "median_lag_interval_upper_hours": q(quantile([r["lag_upper_hours"] for r in adds], .5), "hours"),
       "negative_point_lag": q(sum(r["lag_hours"] < 0 for r in adds), "addresses"),
       "definitely_before_publication": q(sum(r["lag_upper_hours"] < 0 for r in adds), "addresses"),
       "publication_order_ambiguous": q(sum(r["lag_lower_hours"] <= 0 <= r["lag_upper_hours"] for r in adds), "addresses"),
       "share_frozen_before_point_publication": pct(sum(r["lag_hours"] < 0 for r in adds), len(adds)),
       "share_definitely_frozen_before_publication": pct(sum(r["lag_upper_hours"] < 0 for r in adds), len(adds)),
       "known_freeze_balances": q(len(frozen_known), "addresses"),
       "positive_known_freeze_balances": q(sum(r["balance_at_first_freeze_native"] > 0 for r in frozen_known), "addresses"),
       "unknown_freeze_balances": q(len(adds) - len(frozen_known), "addresses"),
       "frozen_native_known_subtotal": q(sum(r["balance_at_first_freeze_native"] for r in frozen_known), "native:" + token),
       "usd_frozen_known_subtotal": q(sum(usd), "usd", "each address's first blacklist timestamp; price observation in CSV"),
       "amount_burned_native": q(sum(r["amount_burned_native"] for r in rows), "native:" + token),
       "usd_burned": q(sum(r["amount_burned_usd"] for r in rows) if all(r["amount_burned_usd"] is not None for r in rows) else None,
                       "usd", "each DestroyedBlackFunds timestamp; price observation in CSV"),
       "escape_native_observed": q(sum(r["escape_native"] for r in escape_known), "native:" + token),
       "escape_native_complete_windows": q(sum(r["escape_native"] for r in escape_complete), "native:" + token),
       "escape_native_publication_earliest": q(sum(r["escape_upper_native"] for r in escape_complete), "native:" + token),
       "escape_native_publication_latest": q(sum(r["escape_lower_native"] for r in escape_complete), "native:" + token),
       "escape_complete_windows": q(len(escape_complete), "addresses"),
       "escape_unknown_windows": q(len(adds) - len(escape_complete), "addresses"),
       "escape_usd_observed": q(sum(r["escape_usd"]["value"] for r in escape_known if r["escape_usd"] and r["escape_usd"]["value"] is not None),
                                "usd", "each outgoing transfer timestamp; gross transfers, including internal cohort transfers"),
       "source_url": "data/derived/freeze_match.csv", "raw_ref": "data/freezes.csv;data/addresses.csv;data/ledger.csv"}
    return result


def build_summaries(rows):
    out = []
    for (issuer, chain), group in sorted(groupby(rows, lambda r: (r["issuer"], r["chain"])).items()):
        for variant, selected in [("all", group), ("excluding_tornado", [r for r in group if not r["tornado_cash"]]),
                                  ("excluding_exchange_scale", [r for r in group if not r["exchange_scale"]]),
                                  ("excluding_tornado_and_exchange_scale", [r for r in group if not r["tornado_cash"] and not r["exchange_scale"]])]:
            out.append(summary(selected, issuer=issuer, chain=chain, program="ALL", year="ALL", variant=variant))
        for year in sorted({r["year"] for r in group}):
            out.append(summary([r for r in group if r["year"] == year], issuer=issuer, chain=chain, program="ALL", year=str(year), variant="all"))
        for program in sorted({p for r in group for p in r["programs"]}):
            out.append(summary([r for r in group if program in r["programs"]], issuer=issuer, chain=chain, program=program, year="ALL", variant="all"))
            for year in sorted({r["year"] for r in group if program in r["programs"]}):
                out.append(summary([r for r in group if program in r["programs"] and r["year"] == year], issuer=issuer, chain=chain, program=program, year=str(year), variant="all"))
    return out


def groupby(rows, key):
    out = collections.defaultdict(list)
    for r in rows:
        out[key(r)].append(r)
    return out


def policy_comparison(rows):
    out = []
    for chain in ("ETH", "TRX"):
        group = [r for r in rows if r["token"] == "USDT" and r["chain"] == chain]
        for label, pred in [("listed before policy decision 2023-12-01", lambda r: r["first_listed_date"] < "2023-12-01"),
                            ("listed on/after public announcement 2023-12-09", lambda r: r["first_listed_date"] >= "2023-12-09")]:
            g = [r for r in group if pred(r)]
            record = summary(g, issuer="tether", chain=chain, cohort=label, year="ALL", program="ALL", variant="all")
            early = [r for r in g if r["blacklisted_ever"]]
            record["first_frozen_on_policy_announcement_date_utc"] = q(sum(r["first_blacklist_utc"][:10] == "2023-12-09" for r in early), "addresses")
            for date in ("2023-11-30", "2023-12-01", "2023-12-08", "2023-12-09"):
                cutoff = time(date + "T23:59:59-05:00")
                record["blacklisted_by_" + date] = q(sum(state_at(r["issuer_events"], cutoff) for r in g), "addresses")
            out.append(record)
    return out


def action_comparison(rows):
    out = []
    for date, group in sorted(groupby([r for r in rows if r["chain"] == "ETH"], lambda r: r["first_listed_date"]).items()):
        paired = []
        for address, rs in groupby(group, lambda r: r["address"]).items():
            by = {r["issuer"]: r for r in rs}
            if set(by) == {"tether", "circle"} and all(by[i]["lag_hours"] is not None for i in by):
                paired.append(by)
        gaps = [p["tether"]["lag_hours"] - p["circle"]["lag_hours"] for p in paired]
        out.append({"action_date": date, "paired_addresses": q(len(paired), "addresses"),
            "circle_first": q(sum(g > 0 for g in gaps), "addresses"), "tether_first": q(sum(g < 0 for g in gaps), "addresses"),
            "median_tether_minus_circle_hours": q(quantile(gaps, .5), "hours"),
            "circle_median_signed_lag_hours": q(quantile([p["circle"]["lag_hours"] for p in paired], .5), "hours"),
            "tether_median_signed_lag_hours": q(quantile([p["tether"]["lag_hours"] for p in paired], .5), "hours"),
            "example_txs": examples([p[i] for p in paired for i in ("circle", "tether")]),
            "raw_ref": "data/derived/freeze_match.csv", "source_url": "https://ofac.treasury.gov/recent-actions/" + date.replace("-", "")})
    return out


def examples(rows, kind="freeze"):
    found, seen = [], set()
    for r in rows:
        txs = r["post_freeze_in_source_cutoff_examples"] if kind == "post_freeze" else r["escape_examples"] if kind == "escape" else [tx_evidence(r["chain"], f) for f in r["issuer_events"]
            if (f["event"] in REMOVES if kind == "remove" else f["event"] in ADDS if kind == "freeze" else True)]
        for tx in txs:
            if tx and tx["hash"] not in seen:
                found.append(tx)
                seen.add(tx["hash"])
                if len(found) == 3:
                    return found
    return found


def claims(rows, freezes, vendors):
    out = []
    relevant_ids = {"CA-ISIS-FREEZE", "EL-GAR-FROZEN", "CIRCLE-TC-BLOCK", "TETHER-POLICY", "TETHER-IRAN-344M",
                    "PAML-ISIS-FROZEN", "PAML-HAMAS-BAL", "BQ-EVENTS", "BQ-OFAC-EXACT", "BQ-REBUILD-ETH",
                    "BQ-REBUILD-TRON", "BQ-LAG-7D", "BQ-CIRCLE-LAG", "PAML-POSTFREEZE-IN"}
    for claim in vendors:
        cid = claim["claim_id"]
        if cid not in relevant_ids:
            continue
        result = {"claim_id": cid, "claim": claim["claim"], "vendor_number": claim["number"], "vendor_unit": claim["unit"],
                  "source_url": claim["url"], "raw_ref": claim["raw_ref"], "verdict": "not_testable_yet",
                  "reason": "", "our_metrics": {}}
        g = []
        if cid == "BQ-EVENTS":
            f = [e for e in freezes if e["token"] == "USDT" and e["event"] in ADDS and e["timestamp"] < "2026-08-13"]
            events, addresses = len(f), len({(e["chain"], e["address_normalized"]) for e in f})
            result["our_metrics"] = {"freeze_events": q(events, "events"), "distinct_chain_addresses": q(addresses, "addresses")}
            result["verdict"] = "agree" if (events, addresses) == (11085, 11045) else "disagree_under_stated_cutoff"
            result["reason"] = "All issuer events, not OFAC-only; cutoff end of 2026-08-12 UTC. Indexer and cutoff conventions remain possible causes of differences."
        elif cid == "BQ-OFAC-EXACT":
            g = [r for r in rows if r["token"] == "USDT" and r["first_listed_date"] <= "2026-08-12" and r["first_blacklist_utc"] and r["first_blacklist_utc"] < "2026-08-13"]
            active = [r for r in g if not r["delisted_date"] or r["delisted_date"] > "2026-08-12"]
            result["our_metrics"] = {"ever_listed_exact_matches": q(len(g), "addresses"), "not_delisted_as_of_cutoff": q(len(active), "addresses")}
            result["verdict"] = "agree" if len(active) == 180 else "disagree_under_public_identifier_cohort"
            result["reason"] = "Exact chain-address join, with historical and as-of-active cohorts separate; no vendor labels are treated as listings. A vendor-labelled subset may be smaller."
        elif cid in {"BQ-LAG-7D", "BQ-CIRCLE-LAG"}:
            issuer = "circle" if cid == "BQ-CIRCLE-LAG" else "tether"
            g = [r for r in rows if r["issuer"] == issuer and r["first_listed_date"] >= "2024-01-01" and
                 r["first_blacklist_utc"] and r["first_blacklist_utc"] < "2026-10-17"]
            lags = [r["lag_hours"] for r in g]
            episodes = [f for r in g for f in r["issuer_events"] if f["event"] in ADDS and "2024-01-01" <= f["timestamp"] < "2026-10-17"]
            share = sum(0 <= x <= 168 for x in lags) / len(lags) if lags else None
            inclusive = sum(x <= 168 for x in lags) / len(lags) if lags else None
            result["our_metrics"] = {"first_freeze_addresses": q(len(g), "addresses"), "freeze_episodes": q(len(episodes), "events"),
                "median_signed_lag_hours": q(quantile(lags, .5), "hours"), "share_0_to_7_days": q(share, "share"),
                "share_no_later_than_7_days_including_prelisting": q(inclusive, "share"),
                "definitely_in_0_to_7_days": q(sum(r["lag_lower_hours"] >= 0 and r["lag_upper_hours"] <= 168 for r in g), "addresses"),
                "possibly_in_0_to_7_days": q(sum(r["lag_lower_hours"] <= 168 and r["lag_upper_hours"] >= 0 for r in g), "addresses")}
            # The saved source table groups by FREEZE period, counts renewed
            # episodes, and deduplicates an add while already frozen. Its day
            # convention is reproducible as calendar-day lag, including all
            # same-day freezes. Do not mistake a negative noon-proxy lag for
            # a day-level disagreement with that table.
            calendar_lags, episode_hours = [], []
            raw_adds, duplicate_adds = 0, 0
            for r in rows:
                if r["issuer"] != issuer:
                    continue
                active = False
                for f in r["issuer_events"]:
                    if f["event"] in REMOVES:
                        active = False
                    elif f["event"] in ADDS:
                        in_period = "2024-01-01" <= f["timestamp"] < "2026-10-17"
                        if in_period:
                            raw_adds += 1
                            duplicate_adds += active
                        if in_period and not active:
                            event_time = time(f["timestamp"])
                            listing_day = time(r["T_pub_utc"]).astimezone(ET).date()
                            calendar_lags.append((event_time.astimezone(ET).date() - listing_day).days)
                            episode_hours.append((event_time - time(r["T_pub_utc"])).total_seconds() / 3600)
                        active = True
            calendar_share = sum(0 <= x <= 7 for x in calendar_lags) / len(calendar_lags) if calendar_lags else None
            result["our_metrics"].update({
                "freeze_period_unique_episodes": q(len(calendar_lags), "events"),
                "freeze_period_raw_add_logs": q(raw_adds, "events"),
                "redundant_adds_while_already_blacklisted": q(duplicate_adds, "events"),
                "calendar_day_0_to_7_episode_count": q(sum(0 <= x <= 7 for x in calendar_lags), "events"),
                "calendar_day_0_to_7_episode_share": q(calendar_share, "share"),
                "episode_median_calendar_days": q(quantile(calendar_lags, .5), "days"),
                "episode_median_noon_proxy_hours": q(quantile(episode_hours, .5), "hours")})
            target = .97 if issuer == "circle" else .76
            result["verdict"] = "agree_under_calendar_day_episode_pairing" if calendar_share is not None and abs(calendar_share - target) < .005 and (issuer != "circle" or len(calendar_lags) == 65) else "disagree_under_calendar_day_episode_pairing"
            result["reason"] = "The saved table groups freezes since 2024, not identifiers first listed since 2024. Replay counts a new freeze after a removal, but excludes redundant adds while already frozen. Calendar-day lag in ET reproduces same-day/next-seven-day shares and median days. Separately shown first-ever noon-proxy results retain signed hours and publication-time uncertainty; the conventions answer different questions."
        elif cid in {"BQ-REBUILD-ETH", "BQ-REBUILD-TRON"}:
            chain = "ETH" if cid.endswith("ETH") else "TRX"
            g = [r for r in rows if r["chain"] == chain and r["token"] == "USDT"]
            tests = [b for r in g for b in r["burn_reconciliation"] if b["testable"]]
            result["our_metrics"] = {"testable_ofac_burns": q(len(tests), "events"), "matching": q(sum(t["match"] for t in tests), "events"),
                                     "share_matching": pct(sum(t["match"] for t in tests), len(tests))}
            result["verdict"] = "not_comparable_population"
            result["reason"] = "Vendor benchmark covers the entire issuer burn population; this analysis has only OFAC-address timelines. An empty or small test set cannot confirm a 99% issuer-wide reconstruction rate."
        elif cid == "EL-GAR-FROZEN":
            g = [r for r in rows if any("GARANTEX" in n for n in r["sdn_names"]) and r["token"] == "USDT"]
            result["our_metrics"] = {"listed_garantex_chain_addresses": q(len(g), "addresses"),
                "known_first_freeze_balances": q(sum(r["balance_at_first_freeze_native"] is not None for r in g), "addresses")}
            result["verdict"] = "not_comparable_population"
            result["reason"] = "The March 2025 takedown cluster and all asset contracts are not disclosed by this claim; OFAC's exact identifiers are a narrower cohort. A first blacklist can predate the takedown."
        elif cid == "TETHER-POLICY":
            g = [r for r in rows if r["issuer"] == "tether" and r["first_listed_date"] < "2023-12-01" and
                 r["first_blacklist_utc"] and r["first_blacklist_utc"][:10] == "2023-12-09"]
            result["our_metrics"] = {"previously_listed_addresses_first_frozen_on_announcement_day": q(len(g), "addresses")}
            result["verdict"] = "agree_on_chain_consequence" if g else "disagree_in_checked_cohort"
            result["reason"] = "A retrospective freeze batch is observable. On-chain timing does not establish motive; decision December 1 and announcement December 9 are distinct."
        elif cid == "CIRCLE-TC-BLOCK":
            g = [r for r in rows if r["issuer"] == "circle" and r["tornado_cash"]]
            same_day = [r for r in g if r["first_blacklist_utc"] and r["first_blacklist_utc"][:10] == "2022-08-08"]
            result["our_metrics"] = {"tornado_identifiers_in_historical_ledger": q(len(g), "addresses"),
                                     "first_blacklisted_2022_08_08_utc": q(len(same_day), "addresses")}
            result["verdict"] = "agree" if same_day else "disagree_in_checked_cohort"
            result["reason"] = "This tests contract blacklisting, not Circle Account access; the issuer page supplies no frozen-dollar target. Later-added identifiers are not assigned an earlier OFAC date."
        else:
            if cid in {"CA-ISIS-FREEZE", "PAML-ISIS-FROZEN", "PAML-POSTFREEZE-IN"}:
                g = [r for r in rows if r["chain"] == "TRX" and r["token"] == "USDT" and "ISIL KHORASAN" in r["sdn_names"] and r["first_listed_date"] == "2026-07-01"]
            elif cid == "PAML-HAMAS-BAL":
                g = [r for r in rows if r["chain"] == "TRX" and r["first_listed_date"] == "2026-07-23" and any("JABURI" in n or "JEBOURI" in n or "JUBURI" in n for n in r["sdn_names"])]
            elif cid == "TETHER-IRAN-344M":
                g = [r for r in rows if r["chain"] == "TRX" and r["first_listed_date"] == "2026-04-24" and any("BANK MARKAZI" in n for n in r["sdn_names"])]
            known = [r for r in g if r["balance_at_first_freeze_native"] is not None]
            result["our_metrics"] = {"cohort": q(len(g), "addresses"), "ever_blacklisted": q(sum(r["blacklisted_ever"] for r in g), "addresses"),
                "known_first_freeze_balances": q(len(known), "addresses"),
                "first_freeze_native_known_subtotal": q(sum(r["balance_at_first_freeze_native"] for r in known), "native:USDT")}
            if cid == "CA-ISIS-FREEZE":
                asof = time("2026-07-01T23:59:59-04:00")
                count = sum(state_at(r["issuer_events"], asof) for r in g)
                result["our_metrics"]["blacklisted_by_end_of_report_day_et"] = q(count, "addresses")
                result["verdict"] = "agree" if len(g) == count == 131 else "disagree_under_ledger_cohort"
                result["reason"] = "Checks blacklist membership by end of report day ET. Empty blacklisted addresses still count; this does not freeze native TRX."
            elif cid == "PAML-POSTFREEZE-IN":
                available = [r for r in g if r["post_freeze_in_source_cutoff_native"] is not None]
                total = sum(r["post_freeze_in_source_cutoff_native"] for r in available)
                result["our_metrics"].update({"histories_available": q(len(available), "addresses"),
                    "inflows_to_blacklisted_addresses_through_2026_10_07_et": q(total, "native:USDT"),
                    "same_ge1usd_at_transfer_time": q(sum(r["post_freeze_in_source_cutoff_ge1usd_native"] for r in available), "native:USDT")})
                result["verdict"] = "not_testable_yet" if len(available) < len(g) else "agree_approximately" if abs(total - 1365) <= 1 else "disagree_under_explicit_cutoff"
                result["reason"] = "Genuine contract receipts while event-derived blacklist state is active. Includes internal cohort transfers; >=1 USD sensitivity shown separately. Source's 'following days' endpoint is unspecified; our bound is end of October 7 ET."
            elif cid == "PAML-HAMAS-BAL":
                at = [r for r in g if r["balance_at_T_native"] is not None]
                total = sum(r["balance_at_T_native"] for r in at)
                result["our_metrics"].update({"known_balances_at_T": q(len(at), "addresses"), "balance_T_native_known_subtotal": q(total, "native:USDT"),
                    "balance_end_of_designation_day_known_subtotal": q(sum(r["balance_at_T_end_native"] for r in at), "native:USDT"),
                    "first_freezes_on_designation_day_et": q(sum(bool(r["first_blacklist_utc"]) and time(r["first_blacklist_utc"]).astimezone(ET).date().isoformat() == "2026-07-23" for r in g), "addresses"),
                    "already_blacklisted_before_designation_day": q(sum(r["lag_upper_hours"] is not None and r["lag_upper_hours"] < 0 for r in g), "addresses")})
                result["verdict"] = "not_testable_yet" if len(g) != 7 or len(at) != len(g) else "agree_approximately" if abs(total - 27.94) < .02 else "disagree_under_T_checkpoint"
                result["reason"] = "T is start of designation day ET; end-of-day total is also reported. Seven historical blacklist matches include six first freezes on designation day and one empty identifier already blacklisted in January 2025. Thus 'six designation-day freezes' and 'seven ever blacklisted' are compatible; the source's implication that the seventh was never blacklisted is not supported by event history. The 1-USDT balance difference remains unreconciled."
            else:
                target = 538270 if cid == "PAML-ISIS-FROZEN" else 344000000
                total = sum(r["balance_at_first_freeze_native"] for r in known)
                tolerance = 1 if cid == "PAML-ISIS-FROZEN" else target * .005
                result["verdict"] = "not_testable_yet" if len(known) != len(g) or not g else "agree_approximately" if abs(total - target) <= tolerance else "disagree_under_first_freeze_reconstruction"
                result["reason"] = "Native USDT balances at each first freeze, not burn amounts or assumed USD parity. Missing, nonreconciling or tied histories prevent full replication."
                if cid == "PAML-ISIS-FROZEN":
                    receipts = sum(r["post_freeze_in_source_cutoff_native"] or 0 for r in g)
                    result["our_metrics"].update({"post_freeze_receipts_through_source_cutoff": q(receipts, "native:USDT"),
                        "first_freeze_plus_post_freeze_receipts": q(total + receipts, "native:USDT"),
                        "vendor_minus_first_freeze_native": q(target - total, "native:USDT")})
                    if len(known) == len(g) and g and abs(total + receipts - target) <= 1:
                        result["reason"] += " The vendor's integer total is reproduced (within one USDT) by first-freeze balances PLUS later receipts through its October 7 read cutoff. This is consistent with a later frozen-account balance, rather than the amount present at freezing."
        result["example_txs"] = examples(g)
        out.append(result)
    # The reference CSV has no Liu §4.2.2 row; test its documented qualitative
    # result separately without inventing a vendor claim or lag target.
    historical = [r for r in rows if r["chain"] == "ETH" and r["first_listed_date"] <= "2025-03-21" and
                  r["first_blacklist_utc"] and r["first_blacklist_utc"] < "2025-03-22"]
    metrics = {}
    for issuer in ("tether", "circle"):
        lags = [r["lag_hours"] for r in historical if r["issuer"] == issuer]
        metrics[issuer] = {"addresses": q(len(lags), "addresses"), "median_signed_lag_hours": q(quantile(lags, .5), "hours"),
                           "p90_signed_lag_hours": q(quantile(lags, .9), "hours")}
    out.append({"claim_id": "LIU-V2-4.2.2", "claim": "USDC delays shorter/less dispersed than USDT (qualitative)",
                "source_url": "https://arxiv.org/pdf/2507.11721v2", "raw_ref": "data/raw/priorart/papers/arxiv-2507-11721-v2.txt.gz#page=5",
                "our_metrics": metrics, "verdict": "qualitatively_agree" if metrics["circle"]["median_signed_lag_hours"]["value"] < metrics["tether"]["median_signed_lag_hours"]["value"] else "qualitatively_disagree",
                "reason": "Historical ETH identifiers through 2025-03-21; not an exact paper-cohort replication. Our noon-ET proxy is 12 hours later than its midnight proxy. Within-block percentage ranks are a different unit and require block transaction totals, unavailable here.",
                "example_txs": examples(historical)})
    return out


def findings(rows, policy, actions):
    out = []
    def add(fid, title, metric, g, confidence, detail, kind="freeze"):
        out.append({"id": fid, "title": title, "metric": metric, "detail": detail,
                    "confidence": confidence, "example_txs": examples(g, kind),
                    "script": "scripts/analysis/freeze_match.py", "raw_ref": "data/derived/freeze_match.csv"})
    pre = [r for r in rows if r["issuer"] == "tether" and r["lag_upper_hours"] is not None and r["lag_upper_hours"] < 0]
    add("issuer-before-ofac", "Tether blacklist precedes even the earliest possible OFAC publication time",
        q(len(pre), "addresses"), sorted(pre, key=lambda r: r["lag_hours"]),
        "High for event/date ordering; not proof of advance notice, motive or coordination.",
        "Distinct ETH/TRX chain-addresses with lag upper bound <0. Same-day noon-negative lags are excluded. Historical/delisted addresses remain included.")
    batch = [r for r in rows if r["issuer"] == "tether" and r["first_listed_date"] < "2023-12-01" and r["first_blacklist_utc"] and r["first_blacklist_utc"][:10] == "2023-12-09"]
    add("tether-retrospective-batch", "Tether's public policy date coincides with a batch of already-listed identifiers",
        q(len(batch), "addresses"), batch, "High for event matching; descriptive policy association, no causal estimate.",
        "Previously listed ETH/TRX identifiers first blacklisted on December 9, 2023 UTC. Long lags reflect retrospective catch-up; pool contracts are separately flagged.")
    eth_tether = [r for r in rows if r["chain"] == "ETH" and r["issuer"] == "tether" and r["lag_hours"] is not None]
    ordinary = [r for r in eth_tether if not r["tornado_cash"]]
    add("tornado-composition-effect", "Tornado Cash changes the Ethereum Tether lag median sharply",
        q(quantile([r["lag_hours"] for r in ordinary], .5), "hours"),
        [r for r in eth_tether if r["tornado_cash"]],
        "High for matched event timestamps; this comparison changes cohort composition and is not an adjusted performance estimate.",
        f"All {len(eth_tether)} valid ever-blacklisted ETH identifiers have median {quantile([r['lag_hours'] for r in eth_tether], .5):,.3f} hours; "
        f"excluding the {sum(r['tornado_cash'] for r in eth_tether)} historical Tornado identifiers gives {len(ordinary)} matched identifiers and the displayed median. "
        "This is why the headline wallet variants exclude Tornado contracts.")
    for issuer in ("tether", "circle"):
        removed = [r for r in rows if r["issuer"] == issuer and r["tornado_cash"] and not r["blacklisted_current"]
                   and any(f["event"] in REMOVES and f["timestamp"].startswith("2025-03") for f in r["issuer_events"])]
        add("tornado-unblacklist-" + issuer, issuer.title() + " removed historical Tornado identifiers after OFAC's March 2025 removal",
            q(len(removed), "addresses"), removed,
            "High for event transitions; removals do not by themselves measure spendability of other assets or establish controller identity.",
            "The ledger's March 21, 2025 removal must not be confused with the superseded UID's November 2022 replacement. "
            "Examples include full lifecycle events in the CSV; removal transaction links are provided here.", "remove")
    pairs = [a for a in actions if a["paired_addresses"]["value"]]
    faster = sum(a["circle_first"]["value"] for a in pairs)
    add("paired-issuer-order", "Circle blacklisted earlier than Tether on matched Ethereum identifiers",
        q(faster, "addresses"), [r for r in rows if r["chain"] == "ETH" and r["first_listed_date"] == "2022-08-08"],
        "High for transaction order; unequal holdings and different policy eras limit performance interpretation.",
        f"Paired denominator: {sum(a['paired_addresses']['value'] for a in pairs)} Ethereum addresses. Same-address issuer timestamps can be compared without knowing intraday OFAC publication time; includes Tornado contracts.")
    escapes = sorted([r for r in rows if r.get("escape_complete") and r["escape_native"] > 0], key=lambda r: -r["escape_native"])
    for chain in ("ETH", "TRX"):
        g = [r for r in escapes if r["token"] == "USDT" and r["chain"] == chain]
        add("escape-usdt-" + chain.lower(), "USDT outgoing volume between noon-ET publication proxy and first freeze on " + chain,
            q(sum(r["escape_native"] for r in g), "native:USDT"), g,
            "Provisional token-history subtotal; publication-day bounds are in summaries. Gross volume may recycle funds and includes dust.",
            f"{len(g)} chain-addresses with observed outgoing transfers in complete token windows. This is transfer volume, not unique money or evidence of intent.", "escape")
    positive = [r for r in rows if r["balance_at_first_freeze_native"] is not None and r["balance_at_first_freeze_native"] > 0]
    for chain, token in CONTRACTS:
        g = sorted([r for r in positive if r["chain"] == chain and r["token"] == token], key=lambda r: -r["balance_at_first_freeze_native"])
        if g:
            add("known-frozen-" + chain.lower() + "-" + token.lower(), "Known first-freeze balances on " + chain + " " + token,
                q(sum(r["balance_at_first_freeze_native"] for r in g), "native:" + token), g,
                "Provisional known-balance subtotal, not a full-population total. Tron latest-state checks are not atomic; sampled historical calls are end-of-block.",
                "Only independently reconciling complete histories or explicit historical balance calls contribute; later destroyed balances are never substituted.")
    iran = [r for r in rows if r["chain"] == "TRX" and r["first_listed_date"] == "2026-04-24" and
            any("BANK MARKAZI" in n for n in r["sdn_names"])]
    known_iran = [r for r in iran if r["balance_at_first_freeze_native"] is not None]
    if known_iran:
        add("iran-two-prelisting-freezes", "Two Iran central-bank identifiers held about 344 million USDT when frozen before their OFAC addition",
            q(sum(r["balance_at_first_freeze_native"] for r in known_iran), "native:USDT"), known_iran,
            "Provisional balance reconstruction matches non-atomic latest Tron observations; event-before-day ordering is high confidence. Only two qualifying freeze transactions exist.",
            "Compare with the issuer's April 23 statement and the official April 24 identifier addition. Exact token amounts and event-time USD observations are in the CSV; no assumption of exact USD parity.")
    jebouri = [r for r in rows if r["chain"] == "TRX" and r["first_listed_date"] == "2026-07-23" and
               any("JEBOURI" in n for n in r["sdn_names"])]
    old = [r for r in jebouri if r["lag_upper_hours"] is not None and r["lag_upper_hours"] < 0]
    if old:
        add("seventh-jebouri-already-frozen", "The seventh Al-Jebouri identifier was already blacklisted before the six July 23 freezes",
            q(len(old), "addresses"), old + [r for r in jebouri if r not in old],
            "High for historical blacklist matching; small balances remain conditional on complete Tron transfer histories. A blacklist says nothing about native TRX.",
            "The 'six newly frozen wallets' observation is compatible with seven ever-blacklisted identifiers: one empty identifier was first blacklisted January 28, 2025. "
            "Our designation balance subtotal differs by about 1 USDT from PublicAML's 27.94 USDT; no cause is inferred.")
    isis = [r for r in rows if r["chain"] == "TRX" and r["first_listed_date"] == "2026-07-01" and
            "ISIL KHORASAN" in r["sdn_names"]]
    known_isis = [r for r in isis if r["balance_at_first_freeze_native"] is not None]
    if isis and len(known_isis) == len(isis):
        receipts = sum(r["post_freeze_in_source_cutoff_native"] or 0 for r in isis)
        caught = sum(r["balance_at_first_freeze_native"] for r in isis)
        add("isis-freeze-versus-later-receipts", "The ISIS-K reported caught balance includes an amount matching later receipts",
            q(receipts, "native:USDT"), [r for r in isis if r["post_freeze_in_source_cutoff_examples"]],
            "Provisional reconstruction of all cohort histories, reconciled to non-atomic latest Tron observations. Arithmetic agreement identifies a compatible timing convention, not the vendor's unpublished calculation.",
            f"{caught:,.6f} USDT was reconstructed at first freeze across {len(isis)} listed Tron identifiers. "
            f"Adding {receipts:,.6f} USDT received while blacklisted through October 7 ET gives {caught + receipts:,.6f} USDT, "
            "which rounds to PublicAML's reported 538,270 USDT 'caught' amount. Distinguish value caught at freeze from later deposits into frozen accounts.", "post_freeze")
    held_never = [r for r in rows if r["token"] == "USDT" and r["held_at_T_or_after"] is True and not r["blacklisted_ever"]]
    add("never-frozen-holders", "Observed USDT holders at/after designation with no blacklist event found",
        q(len(held_never), "addresses"), held_never,
        "Event-history finding within documented ETH/TRX issuer snapshots; missing holdings histories cannot establish a population-wide zero.",
        "This explicit negative-result search is bounded by genuine-contract holdings observations, not inferred from labels.")
    return out


def csv_text(rows):
    fields = list(rows[0])
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: json.dumps(v, sort_keys=True, separators=(",", ":")) if isinstance(v, (dict, list))
                         else str(v).lower() if isinstance(v, bool) else v for k, v in r.items()})
    return out.getvalue()


def markdown(result):
    c = result["coverage"]
    lines = ["# Freeze match — provisional", "", "Generated by `scripts/analysis/freeze_match.py`; offline saved-data analysis. Research, not legal or compliance advice.", "",
       f"**Provisional: {str(result.get('provisional', True)).lower()}.** " + ("Acquisition is still running." if result.get("provisional", True) else "Bounded acquisition finished; per-chain, asset and reconciliation gaps remain.") + " Missing/unreadable/partial timelines never become zero balances. Event-only matches do not depend on timeline completeness.", "",
       "## Coverage and denominators", "",
       f"The ledger contains {c['ledger_chain_addresses']['value']} chain-address pairs; {c['ledger_pairs_with_timeline_on_disk']['value']} have timeline paths on disk (existence, not a claim of readable or complete histories). "
       f"The relevant ETH/TRX inventory has {c['relevant_chain_addresses']['value']} distinct chain-addresses, {c['relevant_readable_timelines']['value']} readable timelines, "
       f"{c['missing_relevant_timelines']['value']} missing and {c['unreadable_or_changed_timelines']['value']} skipped as unreadable, malformed or changing.", "",
       "|Issuer|Chain|All listed addresses|Valid token addresses|Readable timelines|Observed holders at T or after|Holding status unknown|Ever blacklisted|Currently blacklisted|Known freeze balances|Source/raw|",
       "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    overall = [s for s in result["summary"] if s.get("program") == s.get("year") == "ALL" and s["variant"] == "all"]
    for s in overall:
        vals = [s[k]["value"] for k in ("all_ofac_chain_addresses", "valid_token_addresses", "timeline_readable", "observed_holders_at_T_or_after", "holder_status_unknown", "blacklisted_ever", "blacklisted_current", "known_freeze_balances")]
        lines.append("|" + "|".join(map(str, [s["issuer"], s["chain"], *vals, "`data/derived/freeze_match.csv` → row raw refs"])) + "|")
    lines += ["", "ETH USDT and ETH USDC rows describe the same address population; never add their address counts. Program memberships overlap and program subtotals must not be summed. Historical removed strings stay in the denominators. Invalid ledger strings remain visible with `valid_token_address=false` and unknown holdings.", "",
              "Only Ethereum USDT/USDC and Tron USDT are covered. All valid listed 0x strings are unioned onto ETH; a string listed only under another EVM ticker is flagged `same address, other chain`, retains its source-chain date and is separated in coverage metadata. This snapshot's alternate-EVM strings already overlap ETH listings unless reported otherwise.", "",
              "## Candidate findings", ""]
    for f in result["findings"]:
        m = f["metric"]
        lines += [f"### {f['title']}", "", f"**{m['value']:,.6f} {m['unit']}**" if isinstance(m['value'], float) else f"**{m['value']} {m['unit']}**", "", f["detail"], "", "Confidence: " + f["confidence"], ""]
        if f["example_txs"]:
            lines += ["Examples (saved raw reference beside each explorer link):", ""]
            for tx in f["example_txs"]:
                lines.append(f"- [{tx['hash']}]({tx['explorer_url']}) — `{tx['raw_ref']}`")
        else:
            lines.append("No qualifying transaction examples exist for this result; it is not proposed as a positive transaction headline.")
        lines += [""]
    lines += ["## Issuer lag and amounts", "", "|Issuer|Chain|Ever frozen/all|Frozen/observed holders|Median lag h|p90 h|Definitely prepublication|Negative noon-point|Frozen native known subtotal|USD at each first freeze, known subtotal|Burned native|Source/raw|", "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s in overall:
        def v(k):
            x = s[k]["value"]
            return f"{x:,.3f}" if isinstance(x, float) else str(x)
        lines.append(f"|{s['issuer']}|{s['chain']}|{v('blacklisted_ever')}/{v('all_ofac_chain_addresses')}|{v('frozen_observed_holders')}/{v('observed_holders_at_T_or_after')}|{v('median_lag_hours')}|{v('p90_lag_hours')}|{v('definitely_before_publication')}|{v('negative_point_lag')}|{v('frozen_native_known_subtotal')}|{v('usd_frozen_known_subtotal')}|{v('amount_burned_native')}|`data/derived/freeze_match.csv`|")
    lines += ["", "Native amounts are USDT or USDC as identified by issuer, never assumed exactly equal to USD. USD subtotals use `scripts/prices/price.py usd()` at each first-freeze event or destruction event; CSV cells preserve requested time, actual price observation, provider URL and raw response. A sum of event-time valuations has no single common valuation timestamp. Known freeze balances omit unknowns; an apparently small amount is not a full total.", "",
       "All issuer × chain × program × designation-year strata, plus all-chain/program/year marginals, are in `results/freeze_match.json#summary`. Median/p90 use signed first-ever freeze lag, linear-interpolated quantiles, and include empty addresses. Counts and shares are available for all addresses and observed holders at T or after. Wallet-oriented variants exclude Tornado Cash and, separately, >10,000-transaction histories; the latter counts acquired records and is a lower-bound size screen when histories are incomplete.", "",
       "## Policy and paired comparisons", "", "Policy cohorts use first identifier publication before December 1, 2023 and on/after December 9, 2023. They are descriptive cohorts with different ages/composition, not a causal policy estimate. `policy_comparison` includes state at November 30, December 1, December 8 and December 9 ET. `action_comparison` compares Circle/Tether on the same ETH identifiers and OFAC addition action; its issuer timestamp difference cancels unknown publication time.", "",
       "|Chain|Listing cohort|Addresses|Median signed lag h|p90 h|First frozen Dec 9 UTC|Source/raw|", "|---|---|---:|---:|---:|---:|---|"]
    for s in result["policy_comparison"]:
        lines.append(f"|{s['chain']}|{s['cohort']}|{s['all_ofac_chain_addresses']['value']}|{s['median_lag_hours']['value']}|{s['p90_lag_hours']['value']}|{s['first_frozen_on_policy_announcement_date_utc']['value']}|`data/derived/freeze_match.csv`|")
    lines += ["", "## Prior-art tests", "", "`agree`/`disagree` below applies only to the printed cohort, cutoff and event pairing. Partial coverage and undisclosed vendor clusters cannot falsify a larger claim. Prior work already covers freeze timing; this analysis adds reproducible identifier-date joins and explicit uncertainty, not a claim to have invented issuer comparison.", ""]
    for c in result["claim_tests"]:
        lines += [f"### {c['claim_id']}: {c['verdict']}", "", f"Claim: {c['claim']}", "", c["reason"].replace("this analysis has only OFAC-address timelines", "this analysis has only OFAC-address timelines"), "", "Our measurements: `" + json.dumps(c["our_metrics"], sort_keys=True) + "`", "", f"Source: [{c['source_url']}]({c['source_url']}); `{c['raw_ref']}`.", ""]
    lines += ["## Definitions, reconstruction and uncertainties", "",
       "- T is the start of the first-listed calendar day in America/New_York. T_pub point estimate is noon ET; the full interval is [00:00:00, 23:59:59 ET], including DST. Exact ledger timestamps override the date proxy. Lag bounds are event minus latest/earliest publication. A negative noon-point lag alone is not proof that freezing preceded publication.",
       "- First-ever blacklist event is paired to the first address publication, not entity founding/designation. All additions/removals/destructions remain in each CSV row. Current membership replays transitions in chain order; destruction does not remove membership. A removal does not erase an earlier freeze and a subsequent add restores membership.",
       "- Token identity is the canonical contract address plus chain, never symbol. Positive genuine receipts or observed positive balances establish holding; saved historical issuer balance calls can also establish holding even when a timeline is absent. Zero-value/spam-symbol records cannot. No-token conclusions require complete relevant history; principal-only Tornado timelines do not establish other-token absence.",
       "- Historical balances replay complete genuine Transfer history from genesis, subtracting DestroyedBlackFunds only where not already represented by a Transfer debit. Negative states, mismatched present balances or missing observations disable reconstructed amounts. Complete ETH histories must reconcile to independent balanceOf at the same block. Tron matching latest observations are non-atomic and remain conditional; they are not archive calls. Blacklist-event historical balanceOf values are separately labelled end-of-block state, which can differ from pre-log balance.",
       "- Freeze-block transfers require log order on ETH. Missing indexes in that block or a Tron same-timestamp transfer leave the freeze balance unknown. A later burn is valued and reported at its own time, never used as the earlier frozen amount. Circle ordinary minter burns are not frozen-account destruction; see `docs/FREEZES.md` for the implementation-level limitation.",
       "- Escape window means gross genuine-token transfers out strictly after T_pub and strictly before the first freeze. Empty windows for earlier freezes are zero only within checked histories. Complete-window subtotals require token history through freeze; otherwise observed amounts are lower bounds, never proof of no outflow. Earliest/latest publication bounds are reported. Gross volume includes repeated movement, internal cohort transfers and dust; it is not unique funds or a legal conclusion.",
       "- Earliest/latest publication bounds address unknown announcement time, not missing data or chain timestamp uncertainty. No confidence intervals for sampling error are implied: this is an address census with explicit coverage gaps.",
       "- Freeze source completeness is as documented in `docs/FREEZES.md`: Ethereum secondary-indexer gaps, receipt/sample cross-checks, Tron same-indexer paging checks and residual retention uncertainty remain. Other USDT/USDC chains and Solana issuer instructions are outside this analysis.",
        "",
       "## Reproduce", "", "```sh", ".venv/bin/python -B -S scripts/analysis/freeze_match.py", ".venv/bin/python -B -S scripts/analysis/freeze_match.py --check", "```", "",
       "Validation exercised ET winter/summer offsets and exact timestamps; repeated freeze/removal state replay; token-contract filtering; truncated JSON and corrupt gzip skipping; balance at T; escape-window publication bounds; later receipts/burns versus the earlier freeze balance; double-debit prevention when a burn also has a Transfer; and unknown amounts for mismatched balances or missing freeze-block order. Saved-output checks also assert unique address/token keys, evidence-file existence and the compact output size limits.", "",
       "Default execution atomically replaces the analysis outputs. Parsing streams large arrays and skips unreadable, truncated, schema-invalid or concurrently changed timeline files, counting each. Inputs are hashed in the result manifest. `--check` reprocesses saved inputs and compares JSON, CSV and Markdown without writes or network. A timeline refreshed between runs causes a deliberate nonzero diff: rerun the default command and check again after acquisition settles. No keys or network access are required.", ""]
    # Approved public copy; dated sensitivity figures describe the launch snapshot.
    lines += """## Public interpretation and network sensitivity (2026-10-24)

Circle: 216 of 217 historical ETH identifiers ever blacklisted for USDC; one string is malformed. 124 remain blacklisted in the saved event history. The 92 removal events are dated 2025-03-22 (90), 2022-11-10 (one), and 2024-02-06 (one), UTC. The 90 Tornado removals followed the 2025-03-21 delisting; event chronology alone leaves the reasons unresolved. Source: `data/freezes.csv`, matched to `data/ledger.csv`; script: `scripts/release/presentation.py`.

Freeze lag uses noon ET as a proxy. Same-day order is unknown; only events outside the address-listing day establish before/after publication. Dates concern publication of an address identifier; its named entity may already have been designated. Issuer blacklists restrict the issuer token.

Four stablecoin-only ETH identifiers use an Ethereum-convention assignment with medium chain confidence. The fifth medium-confidence row is a Tron-format identifier published under XBT. The public explorer retains chain rules, confidence and source tickers. Excluding the four inferred ETH assignments gives:

| Issuer / token | Historical strings | Ever blacklisted | Still blacklisted | Before listing day | Median lag from noon ET proxy (h) | Median publication-time range (h) | Source |
|---|---:|---:|---:|---:|---:|---|---|
| Circle / USDC | 213 | 212 | 120 | 0 | 8.309722 | -3.69 to 20.309722 | `data/derived/freeze_match.csv`, `data/freezes.csv`, `data/ledger.csv` |
| Tether / USDT | 213 | 212 | 121 | 3 | 9504.079722 | 9492.08 to 9516.079722 | `data/derived/freeze_match.csv`, `data/freezes.csv`, `data/ledger.csv` |

These denominators retain the malformed historical string. The corresponding full-cohort counts and lag summaries remain above. `scripts/release/presentation.py` recomputes this sensitivity from the saved rows during public export.

Every number is reproducible with the included scripts. Raw API captures are omitted for size; `scripts/pipeline.py refresh` re-fetches requests and `rebuild` replays the acquired cache. Public `raw_ref` values identify sources/requests to re-fetch; request metadata is in `data/reference/raw_requests.jsonl.gz` where recoverable.
""".splitlines() + ['']
    if result["skipped_timelines"]:
        lines += ["Skipped timeline details: `" + json.dumps(result["skipped_timelines"], sort_keys=True) + "`", ""]
    return "\n".join(lines)


def run():
    manifest = {}
    paths = ["data/addresses.csv", "data/ledger.csv", "data/freezes.csv", "data/actions.csv", "data/reference/vendor_claims.csv",
             "docs/DEFINITIONS.md", "scripts/prices/price.py", "scripts/analysis/freeze_match.py"]
    paths += [str(p.relative_to(ROOT)) for p in sorted((ROOT / "data/prices").glob("USD[TC]_*.csv.gz"))]
    for p in paths:
        manifest[p] = sha(ROOT / p)
    addresses, ledger, freezes, vendors = (read_csv(p) for p in ("data/addresses.csv", "data/ledger.csv", "data/freezes.csv", "data/reference/vendor_claims.csv"))
    index = groupby(freezes, lambda f: (f["chain"], f["token"], normalize(f["address_normalized"])))
    for es in index.values():
        es.sort(key=event_order)
    eth = {normalize(a["address_normalized"]): dict(a, address_normalized=normalize(a["address_normalized"])) for a in addresses if a["chain"] == "ETH"}
    other_evm = collections.defaultdict(list)
    for a in addresses:
        address = normalize(a["address_normalized"])
        if re.fullmatch("0x[0-9a-f]{40}", address):
            other_evm[address].append(a["chain"])
            if address not in eth:
                eth[address] = dict(a, address_normalized=address, chain="ETH", listing_relation="same address, other chain")
    for address, a in eth.items():
        a["listed_chains"] = ";".join(sorted(set(other_evm.get(address, ["ETH"]))))
    tron = {a["address_normalized"]: a for a in addresses if a["chain"] == "TRX"}
    rows, skipped, coverage = [], [], []
    for chain, group in (("ETH", eth), ("TRX", tron)):
        readable, missing, whole_complete = 0, 0, 0
        for i, (address, a) in enumerate(sorted(group.items())):
            d, path = load_timeline(chain, address, manifest, skipped)
            readable += d is not None
            missing += path is None
            whole_complete += bool(d and d["coverage"].get("complete") is True)
            for token in (("USDT", "USDC") if chain == "ETH" else ("USDT",)):
                rows.append(make_row(a, ledger, chain, token, d, path, index.get((chain, token, address), [])))
            if i % 40 == 0:
                print(f"{chain}: {i + 1}/{len(group)} addresses; readable {readable}", file=sys.stderr, flush=True)
        coverage.append({"chain": chain, "addresses": q(len(group), "addresses"), "readable_timelines": q(readable, "addresses"),
                         "missing_timelines": q(missing, "addresses"), "whole_history_complete": q(whole_complete, "addresses"),
                         "same_address_other_chain_only": q(sum(a.get("listing_relation") == "same address, other chain" for a in group.values()), "addresses"),
                         "raw_ref": "data/derived/freeze_match.csv"})
    rows.sort(key=lambda r: (r["chain"], r["token"], r["address"]))
    # Unique ledger chain-address timeline existence, including untrackable stubs.
    disk_counts = collections.Counter()
    for a in addresses:
        base = ROOT / "data/timelines" / a["chain"].lower()
        address = normalize(a["address_normalized"])
        if any((base / (address + ext)).is_file() for ext in (".json.gz", ".json")):
            disk_counts[a["chain"]] += 1
    policy, actions = policy_comparison(rows), action_comparison(rows)
    result = {"schema_version": "1.0", "provisional": True, "script": "scripts/analysis/freeze_match.py",
              "detail_csv": "data/derived/freeze_match.csv", "analysis_doc": "docs/analysis/FREEZE_MATCH.md",
              "coverage": {"ledger_chain_addresses": q(len(addresses), "addresses"),
                "ledger_pairs_with_timeline_on_disk": q(sum(disk_counts.values()), "addresses"),
                "ledger_timeline_paths_by_chain": {c: q(n, "addresses") for c, n in sorted(disk_counts.items())},
                "relevant_chain_addresses": q(len(eth) + len(tron), "addresses"),
                "relevant_readable_timelines": q(sum(c["readable_timelines"]["value"] for c in coverage), "addresses"),
                "missing_relevant_timelines": q(sum(c["missing_timelines"]["value"] for c in coverage), "addresses"),
                "unreadable_or_changed_timelines": q(len(skipped), "addresses"), "by_chain": coverage,
                "address_token_rows": q(len(rows), "address_token_pairs"),
                "latest_timeline_fetch_utc": max(filter(None, (r["timeline_fetched_at"] for r in rows)), default=None),
                "issuer_history_last_event_utc": {c + ":" + t: max(f["timestamp"] for f in freezes if f["chain"] == c and f["token"] == t) for c, t in CONTRACTS}},
              "units_and_valuation": "Native balances and transfers are token units; USD values are priced at each event/checkpoint using observation at or before requested time. Programs overlap. First-ever freeze lags are signed with ET day bounds.",
              "summary": build_summaries(rows), "policy_comparison": policy, "action_comparison": actions,
              "claim_tests": claims(rows, freezes, vendors), "findings": findings(rows, policy, actions),
              "skipped_timelines": skipped, "input_sha256": dict(sorted(manifest.items()))}
    # Record a signature of the global path-only inventory because fetchers may
    # create an unrelated chain's timeline without affecting relevant raw inputs.
    result["input_sha256"]["ledger_timeline_path_inventory"] = hashlib.sha256(json.dumps(dict(sorted(disk_counts.items())), sort_keys=True).encode()).hexdigest()
    return result, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result, rows = run()
    from scripts.lib.fetch_status import apply_status, report_status
    result = apply_status(result, ROOT, "freeze_match")
    payloads = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", csv_text(rows), report_status(markdown(result), result))
    different = []
    for path, text in zip(OUTPUTS, payloads):
        p = ROOT / path
        if args.check:
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                different.append(path)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.with_name(p.name + f".{os.getpid()}.tmp")
            temp.write_text(text, encoding="utf-8")
            temp.replace(p)
    if different:
        print("CHECK DIFF: " + ", ".join(different) + "; inputs may have refreshed; rerun default command.", file=sys.stderr)
        return 1
    print(("CHECK OK" if args.check else "WROTE") + f": {len(rows)} address-token rows; {result['coverage']['relevant_readable_timelines']['value']} readable relevant timelines; provisional={result['provisional']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
