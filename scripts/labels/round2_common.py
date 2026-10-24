"""Round 2 evidence helpers: inert public responses, bounded requests, no credentials."""
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw/labels2'
OUT = ROOT / 'data/labels'
STARTS = {}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def atomic(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.labels2.tmp')
    temp.write_bytes(body)
    temp.replace(path)


def save_json(path, obj):
    body = (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode()
    atomic(path, gzip.compress(body, mtime=0) if str(path).endswith('.gz') else body)


def read_json(path):
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if str(path).endswith('.gz') else body)


def fetch(url, *, refresh=False):
    if not url.startswith('https://') or any(x in url.lower() for x in ('apikey=', 'api_key=', 'token=')):
        raise ValueError('Only credential-free HTTPS evidence requests')
    meta_path = RAW / 'requests' / (sha(url.encode()) + '.json')
    if meta_path.exists() and not refresh:
        meta = read_json(meta_path)
        body = gzip.decompress((ROOT / meta['raw_ref']).read_bytes())
        assert sha(body) == meta['sha256']
        return body, meta
    host = urllib.parse.urlsplit(url).netloc
    for attempt in range(3):
        time.sleep(max(0, 1.3 - (time.monotonic() - STARTS.get(host, 0))))
        STARTS[host] = time.monotonic()
        request = urllib.request.Request(url, headers={'User-Agent': 'LifeAfterSanctions-public-label-research/2.0', 'Accept': '*/*'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                status, final, headers = response.status, response.url, response.headers
                body = response.read(35_000_001)
        except urllib.error.HTTPError as exc:
            status, final, headers = exc.code, exc.url, exc.headers
            body = exc.read(35_000_001)
            if status in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(min(30, max(2 ** (attempt + 1), int(headers.get('Retry-After', '0')) if headers.get('Retry-After', '0').isdigit() else 0)))
                continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            status, final, headers = 0, url, {}
            body = json.dumps({'transport_error': type(exc).__name__, 'message': str(exc)}).encode()
        if len(body) > 35_000_000:
            raise ValueError('Response exceeds research budget')
        ref = 'data/raw/labels2/objects/' + sha(body) + '.gz'
        atomic(ROOT / ref, gzip.compress(body, mtime=0))
        meta = {'request': {'method': 'GET', 'url': url}, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'http_status': status, 'final_url': final, 'content_type': headers.get('Content-Type'),
                'bytes': len(body), 'sha256': sha(body), 'raw_ref': ref}
        save_json(meta_path, meta)
        return body, meta


def snapshot():
    """Freeze included flow edges without copying the shared 1.4GB CSV."""
    import csv
    import io
    destination = RAW / 'inputs/manifest.json'
    if destination.exists():
        return read_json(destination)
    manifest = {'captured_at': datetime.now(timezone.utc).isoformat(), 'inputs': {}}
    for source in ('results/flows.json', 'data/raw/flows/trace_latest.json.gz', 'data/ledger.csv',
                   'data/labels/labels.csv'):
        path = ROOT / source
        body = path.read_bytes()
        target = RAW / 'inputs' / (path.name if source.endswith('.gz') else path.name + '.gz')
        atomic(target, body if source.endswith('.gz') else gzip.compress(body, mtime=0))
        manifest['inputs'][source] = {'raw_ref': str(target.relative_to(ROOT)), 'sha256': sha(body)}
    path = ROOT / 'data/derived/flows_edges.csv'
    before = path.stat()
    selected, count = [], 0
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        for row in reader:
            count += 1
            if (row['included_in_total'] == 'True' and row['usd'] and row['is_dust'] == 'False'
                    and row['tornado_contract'] == 'False' and row['self_transfer_same_address'] == 'False'):
                selected.append(row)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError('Flow CSV changed while taking snapshot; retry')
    result = read_json(RAW / 'inputs/flows.json.gz')
    from decimal import Decimal
    total = sum((Decimal(r['usd']) for r in selected), Decimal(0))
    assert abs(total - Decimal(str(result['summary']['wallet_outflows_usd']['value']))) < Decimal('.00001')
    assert len(selected) == result['summary']['wallet_outflow_events']['value']
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(selected)
    body = buf.getvalue().encode()
    target = RAW / 'inputs/flows_edges_included.csv.gz'
    atomic(target, gzip.compress(body, mtime=0))
    manifest['inputs']['data/derived/flows_edges.csv'] = {'raw_ref': str(target.relative_to(ROOT)),
        'selection_sha256': sha(body), 'original_size': before.st_size, 'original_mtime_ns': before.st_mtime_ns,
        'original_rows': count, 'included_rows': len(selected), 'included_usd': str(total),
        'filter': 'included_in_total=True; priced; is_dust=False; tornado_contract=False; self_transfer_same_address=False'}
    save_json(destination, manifest)
    return manifest


def edges():
    import csv
    with gzip.open(RAW / 'inputs/flows_edges_included.csv.gz', 'rt', newline='') as stream:
        return list(csv.DictReader(stream))


def ranked():
    from collections import defaultdict
    from decimal import Decimal
    amounts = defaultdict(Decimal)
    for row in edges():
        amounts[row['chain'], row['destination_address']] += Decimal(row['usd'])
    return sorted(({'chain': c, 'address': a, 'usd': str(v)} for (c, a), v in amounts.items()), key=lambda r: (-Decimal(r['usd']), r['chain'], r['address']))


if __name__ == '__main__':
    snapshot()
    print(json.dumps(ranked()[:60], indent=2))
