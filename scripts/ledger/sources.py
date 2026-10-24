"""Content-addressed, gzip-compressed public evidence cache (stdlib only)."""
from __future__ import annotations
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw/ofac'

def atomic(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def index():
    path = RAW / 'manifest.json'
    return json.loads(path.read_text()) if path.exists() else {}

def read(key):
    entry = index()[key]
    return read_entry(entry)

def read_entry(entry):
    body = gzip.decompress((ROOT / entry['raw_ref']).read_bytes())
    if hashlib.sha256(body).hexdigest() != entry['sha256']:
        raise ValueError('Evidence digest mismatch: ' + entry['raw_ref'])
    return body

def fetch(key, url, refresh=False, timeout=90, attempts=5):
    manifest = index()
    if key in manifest and not refresh:
        return read(key)
    if not url.startswith('https://') or any(x in url.lower() for x in ('apikey=', 'token=')):
        raise ValueError('Only public HTTPS requests are supported')
    headers = {'User-Agent': 'LifeAfterSanctionsResearch/1.0 (public evidence archive)',
               'Accept': '*/*', 'Accept-Encoding': 'identity'}
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
                body = resp.read(250_000_001)
                if len(body) > 250_000_000:
                    raise ValueError('Response exceeds 250 MB bound')
                meta = {'url': url, 'final_url': resp.url, 'status': resp.status,
                        'content_type': resp.headers.get('Content-Type'),
                        'last_modified': resp.headers.get('Last-Modified'),
                        'etag': resp.headers.get('ETag')}
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts-1:
                raise
            time.sleep(min(20, 2 ** (attempt + 1)))
        except (TimeoutError, urllib.error.URLError):
            if attempt == attempts-1:
                raise
            time.sleep(min(20, 2 ** (attempt + 1)))
    digest = hashlib.sha256(body).hexdigest()
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    path = RAW / 'objects' / (digest + '.gz')
    if not path.exists():
        atomic(path, gzip.compress(body, mtime=0))
    meta.update(fetched_at=stamp, sha256=digest, bytes=len(body),
                raw_ref=str(path.relative_to(ROOT)))
    # Retain earlier fetch metadata too: refreshing never discards old evidence.
    with (RAW / '.manifest.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        history_path = RAW / 'fetches.jsonl'
        with history_path.open('a') as out:
            out.write(json.dumps(dict(key=key, **meta), sort_keys=True) + '\n')
        manifest = index()
        manifest[key] = meta
        atomic(RAW / 'manifest.json', (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
    print(f'cached {key}: {len(body):,} bytes', flush=True)
    return body

if __name__ == '__main__':
    import sys
    fetch(sys.argv[1], sys.argv[2], '--refresh' in sys.argv[3:])
