"""Standard-library evidence cache. Never serialize the Etherscan secret."""
from __future__ import annotations

import gzip
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/evm"


def acquire_chain_locks(chains):
    """Nonblocking OS locks prevent two EVM commands rewriting the same chain."""
    directory = RAW / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    handles = []
    try:
        for chain in sorted(set(chains)):
            if not chain.isalnum():
                raise ValueError("Invalid chain lock name")
            handle = (directory / f"{chain}.lock").open("a+")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                raise RuntimeError(f"Another EVM command is writing chain {chain}; wait for it to finish")
            handles.append(handle)
        return handles
    except BaseException:
        for handle in handles:
            handle.close()
        raise


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{threading.get_ident()}.tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as f:
        json.dump(value, f, separators=(",", ":"), ensure_ascii=False)
    temp.replace(path)


def read_json(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def has_error(response):
    if isinstance(response, dict):
        return "error" in response or (response.get("status") == "0" and not isinstance(response.get("result"), list))
    return isinstance(response, list) and any(isinstance(item, dict) and "error" in item for item in response)


def api_key():
    key = os.environ.get("ETHERSCAN_API_KEY", "")
    return key


class APIError(RuntimeError):
    def __init__(self, message, raw_ref=None):
        super().__init__(message)
        self.raw_ref = raw_ref


class Client:
    def __init__(self, timeout=30):
        self.key = api_key()
        self.timeout = timeout
        self.lock = threading.Lock()
        self.last_request = {}
        self.host_intervals = {}
        self.network_calls = 0
        self.session = now()

    def redact(self, value):
        text = json.dumps(value, ensure_ascii=False)
        if self.key:
            text = text.replace(self.key, "REDACTED")
        return json.loads(text)

    def request(self, source, url, params=None, body=None, fresh=False, attempts=3):
        params = dict(params or {})
        clean = {k: v for k, v in params.items() if k.lower() not in {"apikey", "api_key"}}
        request = {"method": "POST" if body is not None else "GET", "url": url}
        if clean:
            request["params"] = clean
        if body is not None:
            request["body"] = body
        identity = dict(request)
        if fresh:
            identity["observation"] = time.time_ns()
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        path = RAW / source / (digest + ".json.gz")
        ref = str(path.relative_to(ROOT))
        if path.exists():
            saved = read_json(path)
            response = saved["response"]
            semantic_error = has_error(response)
            if saved["status"] == 200 and not semantic_error:
                return saved["response"], ref
            # Preserve legacy cache errors before any successful retry replaces
            # the stable request slot. New errors get their own observation ID.
            old_digest = hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()[:16]
            old_path = path.with_name(f"{digest}.legacy-error-{old_digest}.json.gz")
            if not old_path.exists():
                save_json(old_path, saved)
        for attempt in range(attempts):
            if self.network_calls % 250 == 0:
                # Shared project cap is 10 GB; stop below it to leave headroom
                # for concurrent processes and the response currently being fetched.
                size = sum(p.stat().st_size for p in (ROOT / "data").rglob("*") if p.is_file())
                if size > 8_800_000_000:
                    raise APIError("Shared data directory exceeds 8.8 GB; fetch paused before 10 GB project budget", ref)
            # Shared across all threads, safely below this process’s 2.5 req/s budget.
            host = urllib.parse.urlsplit(url).netloc
            base_interval = 0.6 if "etherscan.io" in host else 0.7 if "blockscout.com" in host else 0.6 if "drpc.org" in host else 0.5 if host in {"mainnet.base.org", "mainnet.optimism.io"} or "public.blastapi.io" in host else 0.15
            with self.lock:
                interval = self.host_intervals.get(host, base_interval)
                delay = interval - (time.monotonic() - self.last_request.get(host, 0))
                if delay > 0:
                    time.sleep(delay)
                self.last_request[host] = time.monotonic()
                self.network_calls += 1
            if "etherscan.io" in host:
                # All commands in this analysis share one start-rate allocation.
                # The other job sharing the key has its own separate budget.
                RAW.mkdir(parents=True, exist_ok=True)
                with (RAW / ".etherscan-rate.lock").open("a+") as rate:
                    fcntl.flock(rate.fileno(), fcntl.LOCK_EX)
                    rate.seek(0)
                    try:
                        last = float(rate.read().strip() or "0")
                    except ValueError:
                        last = 0
                    delay = 0.6 - (time.time() - last)
                    if 0 < delay <= 0.6:
                        time.sleep(delay)
                    rate.seek(0)
                    rate.truncate()
                    rate.write(str(time.time()))
                    rate.flush()
                    fcntl.flock(rate.fileno(), fcntl.LOCK_UN)
            target = url + (("?" + urllib.parse.urlencode(params)) if params else "")
            headers = {"User-Agent": "LifeAfterSanctions/1.0 public-chain-research", "Accept": "application/json"}
            data = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                data = json.dumps(body).encode()
            try:
                with urllib.request.urlopen(urllib.request.Request(target, data=data, headers=headers), timeout=self.timeout) as response:
                    status, content = response.status, response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as exc:
                status, content = exc.code, exc.read().decode("utf-8", errors="replace")
            except (OSError, TimeoutError) as exc:
                status, content = 0, type(exc).__name__
            try:
                payload = json.loads(content)
            except ValueError:
                payload = content
            saved = self.redact({"request": request, "retrieved_at": now(), "status": status, "response": payload})
            # Keep failed attempts as independent evidence; successful retries keep stable refs.
            successful = status == 200 and not has_error(saved["response"])
            attempt_path = path if successful else path.with_name(f"{digest}.attempt{attempt}-{time.time_ns()}.json.gz")
            save_json(attempt_path, saved)
            attempt_ref = str(attempt_path.relative_to(ROOT))
            if status == 200:
                semantic_rate = has_error(saved["response"]) and any(phrase in str(saved["response"]).lower() for phrase in ("rate limit", "too many requests", "per second capacity", "per second request", "/second request limit"))
                if semantic_rate and attempt + 1 < attempts:
                    with self.lock:
                        self.host_intervals[host] = min(self.host_intervals.get(host, base_interval) * 2, 8)
                        self.last_request[host] = time.monotonic() + 2 ** (attempt + 1)
                    continue
                semantic_outage = has_error(saved["response"]) and any(phrase in str(saved["response"]).lower() for phrase in ("temporarily unavailable", "internal server error", "'message': 'internal error'"))
                if semantic_outage and attempt + 1 < attempts:
                    time.sleep(2 ** (attempt + 1))
                    continue
                return saved["response"], attempt_ref
            if status == 429:
                with self.lock:
                    self.host_intervals[host] = min(self.host_intervals.get(host, base_interval) * 2, 8)
                    self.last_request[host] = time.monotonic() + 10
            if status in {0, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                time.sleep(min(2 ** (attempt + 1), 8))
                continue
            raise APIError(f"HTTP {status} from {host}: {str(saved['response'])[:160]}", attempt_ref)
        raise APIError("Request exhausted retries", ref)

    def etherscan(self, chain_id, action, **params):
        for attempt in range(3):
            payload, ref = self.request("etherscan", "https://api.etherscan.io/v2/api", {
                "chainid": chain_id, "module": "account", "action": action, **params, "apikey": self.key,
            })
            if "rate limit" not in str(payload).lower() or attempt == 2:
                break
            time.sleep(2 ** (attempt + 1))
        if not isinstance(payload, dict):
            raise APIError("Non-object Etherscan response", ref)
        if payload.get("status") == "1" or (payload.get("status") == "0" and isinstance(payload.get("result"), list) and not payload["result"]):
            return payload["result"], ref
        raise APIError(str(payload.get("result") or payload.get("message") or payload)[:220], ref)

    def rpc(self, url, method, params, fresh=False):
        payload, ref = self.request("rpc", url, body={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, fresh=fresh)
        if not isinstance(payload, dict) or "error" in payload or "result" not in payload:
            raise APIError(str(payload)[:220], ref)
        return payload["result"], ref

    def batch(self, url, calls, fresh=False):
        body = [{"jsonrpc": "2.0", "id": i, "method": method, "params": params} for i, (method, params) in enumerate(calls)]
        payload, ref = self.request("rpc", url, body=body, fresh=fresh)
        if not isinstance(payload, list):
            raise APIError(str(payload)[:220], ref)
        indexed = {x["id"]: x for x in payload}
        return [(indexed.get(i, {}).get("result"), indexed.get(i, {}).get("error")) for i in range(len(calls))], ref
