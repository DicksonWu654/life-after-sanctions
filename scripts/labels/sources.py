"""Small, credential-free, resumable public-data fetcher (standard library only)."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/labels"


def fetch(url: str, *, refresh: bool = False) -> tuple[bytes, str]:
    """Cache unmodified response bytes, request, timestamp and digest; never execute data."""
    if not url.startswith("https://") or any(s in url.lower() for s in ("apikey=", "api_key=", "token=")):
        raise ValueError("Only credential-free HTTPS sources are permitted")
    key = hashlib.sha256(url.encode()).hexdigest()
    meta = RAW / "requests" / (key + ".json")
    if meta.exists() and not refresh:
        metadata = json.loads(meta.read_text())
        target = ROOT / metadata["raw_ref"]
        if target.exists():
            payload = gzip.decompress(target.read_bytes())
            if hashlib.sha256(payload).hexdigest() != metadata["sha256"]:
                raise ValueError("Cached source digest mismatch")
            return payload, metadata["raw_ref"]
    request = urllib.request.Request(url, headers={"User-Agent": "LifeAfterSanctions-label-research/1.0", "Accept": "*/*"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read(40_000_001)
                if len(payload) > 40_000_000:
                    raise ValueError("Response exceeds per-file research budget")
                digest = hashlib.sha256(payload).hexdigest()
                target = RAW / "objects" / (digest + ".gz")
                metadata = {
                    "request": {"method": "GET", "url": url},
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "http_status": response.status,
                    "final_url": response.url,
                    "content_type": response.headers.get("Content-Type"),
                    "sha256": digest,
                    "bytes": len(payload),
                    "raw_ref": str(target.relative_to(ROOT)),
                }
            target.parent.mkdir(parents=True, exist_ok=True)
            meta.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(gzip.compress(payload, mtime=0))
            temporary.replace(target)
            meta.write_text(json.dumps(metadata, indent=2) + "\n")
            return payload, metadata["raw_ref"]
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise
            try:
                retry_after = int(exc.headers.get("Retry-After", "0"))
            except ValueError:
                retry_after = 0
            time.sleep(min(30, max(2 ** attempt, retry_after)))
        except (TimeoutError, urllib.error.URLError):
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Unreachable")


def github_pin(repo: str, branch: str) -> tuple[str, dict, dict]:
    """Resolve an explicitly selected upstream before retrieving individual data files."""
    metadata = json.loads(fetch(f"https://api.github.com/repos/{repo}")[0])
    commit = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/{branch}")[0])["sha"]
    tree = json.loads(fetch(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1")[0])
    if tree.get("truncated"):
        raise ValueError(f"Incomplete tree for {repo}")
    return commit, metadata, tree


def github_file(repo: str, commit: str, path: str) -> tuple[bytes, str]:
    return fetch(f"https://raw.githubusercontent.com/{repo}/{commit}/{path}")
