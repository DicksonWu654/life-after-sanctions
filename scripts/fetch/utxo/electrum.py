"""Small read-only Electrum client and BCH native transaction decoder.

Only server.version, scripthash.get_history/get_balance, transaction.get and
block.header are used. TLS certificate validation remains enabled.
"""
import hashlib
import json
import socket
import ssl
import struct
import time

from fetch import RAW, FetchError, write_json, read_json, rel, now, sat, normalize_tx, new_timeline, finish, cache_snapshot

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def bitcoin_address_error(address):
    """Validate mainnet Base58Check and BIP173/BIP350 witness addresses."""
    try:
        if address.startswith(('1', '3')):
            address_script(address)  # Same P2PKH/P2SH versions and checksum as BCH.
            return None
        if not address.lower().startswith('bc1'):
            return 'Not a Bitcoin mainnet Base58Check or bc1 witness address'
        if address != address.lower() and address != address.upper():
            return 'Mixed-case Bitcoin witness address'
        text = address.lower()
        data = [CHARSET.index(c) for c in text[3:]]
        if len(text) > 90 or len(data) < 7 or data[0] > 16:
            return 'Invalid Bitcoin witness address length/version'
        check = 1
        values = [ord(c) >> 5 for c in 'bc'] + [0] + [ord(c) & 31 for c in 'bc'] + data
        for value in values:
            top = check >> 25
            check = ((check & 0x1ffffff) << 5) ^ value
            for i, generator in enumerate([0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]):
                if (top >> i) & 1:
                    check ^= generator
        expected = 1 if data[0] == 0 else 0x2bc830a3
        if check != expected:
            return 'Invalid Bitcoin witness checksum'
        program = convertbits(data[1:-6], 5, 8, False)
        if not 2 <= len(program) <= 40 or (data[0] == 0 and len(program) not in (20, 32)):
            return 'Invalid Bitcoin witness program length'
        return None
    except (ValueError, IndexError):
        return 'Invalid Bitcoin address encoding/checksum'


def double_hash(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def convertbits(values, source, dest, pad=True):
    value, bits, result = 0, 0, []
    for n in values:
        if n < 0 or n >> source:
            raise ValueError("Invalid address data")
        value = (value << source) | n
        bits += source
        while bits >= dest:
            bits -= dest
            result.append((value >> bits) & ((1 << dest) - 1))
    if pad and bits:
        result.append((value << (dest - bits)) & ((1 << dest) - 1))
    elif not pad and (bits >= source or ((value << (dest - bits)) & ((1 << dest) - 1))):
        raise ValueError("Nonzero address padding")
    return bytes(result)


def polymod(values):
    checksum = 1
    generators = [0x98F2BC8E61, 0x79B76D99E2, 0xF33E5FB3C4, 0xAE2EABE2A8, 0x1E4F43E470]
    for v in values:
        top = checksum >> 35
        checksum = ((checksum & 0x07FFFFFFFF) << 5) ^ v
        for i, g in enumerate(generators):
            if (top >> i) & 1:
                checksum ^= g
    return checksum ^ 1


def address_script(address):
    if address.startswith(("1", "3")):
        value = 0
        for c in address:
            value = value * 58 + BASE58.index(c)
        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        raw = b"\0" * (len(address) - len(address.lstrip("1"))) + raw
        if len(raw) != 25 or double_hash(raw[:-4])[:4] != raw[-4:]:
            raise ValueError("Invalid legacy BCH address checksum")
        kind, h = raw[0], raw[1:-4]
        if kind not in (0, 5):
            raise ValueError("Unexpected legacy BCH address version")
        return (b"\x76\xa9\x14" + h + b"\x88\xac") if kind == 0 else b"\xa9\x14" + h + b"\x87"
    prefix, payload = address.split(":", 1) if ":" in address else ("bitcoincash", address)
    values = [CHARSET.index(c) for c in payload.lower()]
    if polymod([ord(c) & 31 for c in prefix] + [0] + values) != 0:
        raise ValueError("Invalid BCH cashaddr checksum")
    raw = convertbits(values[:-8], 5, 8, False)
    if len(raw) != 21 or raw[0] not in (0, 8):
        raise ValueError("Unsupported BCH cashaddr version/size")
    return (b"\x76\xa9\x14" + raw[1:] + b"\x88\xac") if raw[0] == 0 else b"\xa9\x14" + raw[1:] + b"\x87"


def script_address(script):
    if len(script) == 25 and script.startswith(b"\x76\xa9\x14") and script.endswith(b"\x88\xac"):
        raw = b"\0" + script[3:23]
    elif len(script) == 23 and script.startswith(b"\xa9\x14") and script.endswith(b"\x87"):
        raw = b"\x08" + script[2:22]
    else:
        return []
    values = list(convertbits(raw, 8, 5))
    mod = polymod([ord(c) & 31 for c in "bitcoincash"] + [0] + values + [0] * 8)
    check = [(mod >> (5 * (7 - i))) & 31 for i in range(8)]
    return ["bitcoincash:" + "".join(CHARSET[v] for v in values + check)]


def decode_tx(raw_hex):
    data = bytes.fromhex(raw_hex)
    offset = 4
    def take(n):
        nonlocal offset
        if offset + n > len(data):
            raise ValueError("Truncated BCH transaction")
        part = data[offset:offset+n]
        offset += n
        return part
    def varint():
        first = take(1)[0]
        return first if first < 253 else int.from_bytes(take({253: 2, 254: 4, 255: 8}[first]), "little")
    inputs, outputs = [], []
    for _ in range(varint()):
        txid = take(32)[::-1].hex()
        vout = int.from_bytes(take(4), "little")
        take(varint())
        take(4)
        inputs.append({"txid": txid, "vout": vout})
    for n in range(varint()):
        value = int.from_bytes(take(8), "little")
        script = take(varint())
        outputs.append({"value": value, "script": script, "n": n})
    take(4)
    if offset != len(data):
        raise ValueError("Unparsed bytes in BCH transaction")
    return {"txid": double_hash(data)[::-1].hex(), "vin": inputs, "vout": outputs}


class Electrum:
    def __init__(self, client, host="bch.imaginary.cash", port=50002):
        self.client, self.host, self.port = client, host, port
        self.socket = self.file = None

    def close(self):
        if self.file:
            self.file.close()
        if self.socket:
            self.socket.close()
        self.file = self.socket = None

    def call(self, method, params, fresh=False):
        req = {"id": 1, "method": method, "params": params}
        url = f"ssl://{self.host}:{self.port}"
        key = hashlib.sha256(json.dumps([url, req], sort_keys=True).encode()).hexdigest()
        path = RAW / self.host / key[:2] / (key + ".json.gz")
        if path.exists() and not fresh:
            cached = read_json(path)
            if "result" in cached.get("response", {}) and cached["response"].get("error") is None:
                snapshot = path.with_name(key + "-" + hashlib.sha256(json.dumps(cached, sort_keys=True).encode()).hexdigest()[:16] + ".json.gz")
                return cached["response"]["result"], rel(snapshot) + "#response.result"
        with self.client.lock:
            delay = max(0, self.client.next_at.get(self.host, 0) - time.monotonic())
            self.client.next_at[self.host] = time.monotonic() + delay + self.client.interval
            self.client.network_calls += 1
            self.client.request_log.append({"url": url, "method": method, "params": params})
        if delay:
            time.sleep(delay)
        result = None
        try:
            if self.socket is None:
                sock = socket.create_connection((self.host, self.port), timeout=30)
                self.socket = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                self.file = self.socket.makefile("rb")
            self.socket.sendall((json.dumps(req) + "\n").encode())
            # Fulcrum may send notifications; accept only our response ID.
            for _ in range(20):
                line = self.file.readline(100 * 1024 * 1024)
                result = json.loads(line)
                if result.get("id") == 1:
                    break
            else:
                raise ValueError("No matching Electrum response ID")
        except (OSError, ValueError) as exc:
            result = {"error": str(exc)}
            self.close()
        envelope = {"request": {"url": url, "jsonrpc": req}, "fetched_at": now(), "response": result}
        snapshot = path.with_name(key + "-" + hashlib.sha256(json.dumps(envelope, sort_keys=True).encode()).hexdigest()[:16] + ".json.gz")
        write_json(snapshot, envelope)
        cache_snapshot(snapshot, path)
        ref = rel(snapshot) + "#response.result"
        if "result" not in result or result.get("error") is not None:
            raise FetchError(f"Electrum {method}: {result.get('error')}", ref)
        return result["result"], ref


def fetch_bch(client, row, old, refresh):
    ec = Electrum(client)
    address = row["address"]
    own_script = address_script(address)
    script_hash = hashlib.sha256(own_script).digest()[::-1].hex()
    timeline = new_timeline(row, f"ssl://{ec.host}:{ec.port}")
    try:
        balance, bref = ec.call("blockchain.scripthash.get_balance", [script_hash], fresh=bool(old))
        history, href = ec.call("blockchain.scripthash.get_history", [script_hash], fresh=bool(old))
        timeline["history_raw_ref"] = href
        timeline["address_script_hex"] = own_script.hex()
        known = {t["hash"]: t for t in old["txs"] if t.get("block")} if old else {}
        for h in history:
            txid = h["tx_hash"]
            if txid in known:
                timeline["txs"].append(known[txid])
                continue
            raw, ref = ec.call("blockchain.transaction.get", [txid])
            tx = decode_tx(raw)
            if tx["txid"] != txid:
                raise FetchError("Electrum raw transaction hash mismatch", ref)
            prev_refs = []
            for vin in tx["vin"]:
                if vin["txid"] == "0" * 64:
                    vin["value"], vin["addresses"] = 0, []
                    continue
                raw_prev, pref = ec.call("blockchain.transaction.get", [vin["txid"]])
                prev = decode_tx(raw_prev)
                if prev["txid"] != vin["txid"]:
                    raise FetchError("Electrum prevout transaction hash mismatch", pref)
                v = prev["vout"][vin["vout"]]
                vin["value"] = v["value"]
                vin["addresses"] = [address] if v["script"] == own_script else script_address(v["script"])
                prev_refs.append(pref)
            for v in tx["vout"]:
                v["addresses"] = [address] if v["script"] == own_script else script_address(v["script"])
            tx["fees"] = max(0, sum(v["value"] for v in tx["vin"]) - sum(v["value"] for v in tx["vout"]))
            tx["blockHeight"] = h["height"]
            if h["height"] > 0:
                header, header_ref = ec.call("blockchain.block.header", [h["height"]])
                tx["blockTime"] = struct.unpack("<I", bytes.fromhex(header)[68:72])[0]
            else:
                header_ref = None
            t = normalize_tx("bch", address, tx, ref, "blockbook")
            t["prevout_raw_refs"], t["header_raw_ref"] = prev_refs, header_ref
            timeline["txs"].append(t)
        return finish(timeline, sum(h["height"] > 0 for h in history), balance["confirmed"], bref, complete=True,
                      notes=["BCH Electrum scripthash history; native BCH only. CashTokens/SLP metadata is not parsed. Legacy and CashAddr encodings matched by locking script."],
                      unconfirmed=balance.get("unconfirmed", 0))
    finally:
        ec.close()
