"""Standard-library-only, evidence-preserving HTTP and timeline utilities."""
from __future__ import annotations
import csv
import fcntl
import gzip
import hashlib
import json
import re
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal,localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def utc(ms):
    return datetime.fromtimestamp(int(ms) / 1000, timezone.utc).isoformat().replace('+00:00', 'Z')

def amount(value, decimals=6):
    with localcontext() as ctx:
        ctx.prec=max(100,len(str(value))+abs(int(decimals))+10)
        return format(Decimal(str(value)) / Decimal(10) ** int(decimals), 'f')

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    os.close(fd)
    tmp=Path(name)
    # Timelines are checkpointed after each page. Fast gzip keeps large wallets
    # resumable without repeatedly spending seconds recompressing the same rows.
    try:
        with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=1) as f:
            json.dump(value, f, separators=(',', ':'), ensure_ascii=False)
        tmp.replace(path)
    finally:tmp.unlink(missing_ok=True)

def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return json.load(f)

class FetchError(Exception):
    pass

class BusyAddress(FetchError):
    pass

def acquire_address_lock(chain,address):
    source='tron' if chain=='trx' else 'other'
    directory=ROOT/'data/raw'/source/'locks'
    directory.mkdir(parents=True,exist_ok=True)
    f=(directory/(chain+'-'+address+'.lock')).open('a+')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        raise BusyAddress('Address already has an active fetch writer: '+chain+' '+address)
    return f

class Client:
    def __init__(self, source='tron', delay=1.2, retries=3, timeout=35):
        self.source, self.delay, self.retries, self.timeout = source, delay, retries, timeout
        self.last = {}
        self.calls = self.hits = 0
        self.errors = []

    def get(self, url, params=None, **kw):
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(sorted(params.items()))
        return self.request(url, **kw)

    def rate_gate(self,host):
        if host!='api.trongrid.io':return
        # Observed public quota: 1 request/second. A shared advisory lock also
        # coordinates independent address partitions using this same client.
        directory=ROOT/'data/raw/tron/rate-limit'
        directory.mkdir(parents=True,exist_ok=True)
        with (directory/'trongrid.lock').open('a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            f.seek(0)
            try:last=float(f.read() or '0')
            except ValueError:last=0
            current=time.time()
            if last>current+5:last=0
            cooldown=directory/'trongrid.cooldown'
            try:not_before=float(cooldown.read_text())
            except (OSError,ValueError):not_before=0
            time.sleep(max(0,min(45,max(last+1.2,not_before)-current)))
            f.seek(0);f.truncate();f.write(str(time.time()));f.flush()
            fcntl.flock(f,fcntl.LOCK_UN)

    def shared_backoff(self,host,seconds):
        if host!='api.trongrid.io':return
        directory=ROOT/'data/raw/tron/rate-limit'
        directory.mkdir(parents=True,exist_ok=True)
        with (directory/'trongrid.lock').open('a+') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            path=directory/'trongrid.cooldown'
            try:previous=float(path.read_text())
            except (OSError,ValueError):previous=0
            path.write_text(str(max(previous,time.time()+seconds)))
            fcntl.flock(f,fcntl.LOCK_UN)

    def request(self, url, payload=None, group='api', fresh=False, preserve_text=False):
        # Never accept secrets in saved request metadata.
        if re.search(r'(?i)(apikey|api_key|api-key|token|secret)=', url):
            raise ValueError('Credential-bearing URL refused')
        method = 'POST' if payload is not None else 'GET'
        identity = json.dumps([method, url, payload], sort_keys=True, separators=(',', ':'))
        key = hashlib.sha256(identity.encode()).hexdigest()
        base = ROOT / 'data/raw' / self.source / group
        path = base / (key + '.json.gz')
        if path.exists() and not fresh:
            obj = load(path)
            self.hits += 1
            return obj['response'], str(path.relative_to(ROOT))
        if fresh:
            path = base / (key + '-' + str(time.time_ns()) + '.json.gz')
        host = urllib.parse.urlsplit(url).netloc
        for attempt in range(self.retries + 1):
            # TronGrid already has a process-shared 1.2s request-start gate.
            # A second delay after response completion needlessly adds network
            # latency to every incremental tail call. Preserve larger overrides.
            if host != 'api.trongrid.io' or self.delay > 1.2:
                time.sleep(max(0, self.last.get(host, 0) + self.delay - time.monotonic()))
            self.rate_gate(host)
            headers = {'User-Agent': 'LifeAfterSanctions-research/1.0', 'Accept': 'application/json'}
            data = None
            if payload is not None:
                data = json.dumps(payload).encode()
                headers['Content-Type'] = 'application/json'
            status, body = 0, ''
            requested_at = now()
            try:
                self.calls += 1
                with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=self.timeout) as r:
                    status, body = r.status, r.read().decode('utf-8', errors='replace')
            except urllib.error.HTTPError as e:
                status, body = e.code, e.read().decode('utf-8', errors='replace')
            except (OSError, TimeoutError) as e:
                body = str(e)
            self.last[host] = time.monotonic()
            try:
                response = json.loads(body)
            except (ValueError, TypeError):
                response = body
            envelope = {'requested_at': requested_at, 'request': {'method': method, 'url': url, 'json': payload},
                        'http_status': status, 'response': response}
            if preserve_text:envelope['response_text']=body
            if 200 <= status < 300:
                save(path, envelope)
                return response, str(path.relative_to(ROOT))
            err_path = base / 'errors' / (key + '-' + str(time.time_ns()) + '.json.gz')
            save(err_path, envelope)
            detail = {'status': status, 'url': url, 'raw_ref': str(err_path.relative_to(ROOT))}
            self.errors.append(detail)
            if status not in (0, 408, 429, 500, 502, 503, 504) or attempt == self.retries:
                raise FetchError(json.dumps(detail))
            wait = min(45, 6 * 2 ** attempt)
            if status==429:self.shared_backoff(host,wait)
            print(f'HTTP {status}: backing off {wait}s ({host})', flush=True)
            time.sleep(wait)
        raise AssertionError('unreachable')

def addresses(path):
    aliases = {'tron':'trx', 'solana':'sol', 'ripple':'xrp', 'monero':'xmr'}
    result = {}
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            chain = aliases.get(row['chain'].lower(), row['chain'].lower())
            addr = row.get('address_normalized') or row.get('address')
            if not addr or not re.fullmatch(r'[A-Za-z0-9:._-]+', addr):
                raise ValueError('Unsafe or empty address')
            result[(chain, addr)] = dict(row, chain=chain, address=addr)
    return list(result.values())

def timeline_path(chain, addr):
    return ROOT / 'data/timelines' / chain / (addr + '.json.gz')

def blank(chain, addr, source):
    return {'chain':chain, 'address':addr, 'fetched_at':now(), 'source':source,
            'coverage':{'from_block':None, 'from_time':None, 'to_block':None, 'to_time':None,
                        'complete':False, 'notes':[]}, 'txs':[], 'balance_now':[]}

def set_bounds(timeline):
    txs = timeline['txs']
    for key, field in [('block', 'block'), ('time', 'time_utc')]:
        vals = [t[field] for t in txs if t.get(field) is not None]
        if vals:
            timeline['coverage']['from_' + key] = min(vals)
            timeline['coverage']['to_' + key] = max(vals)
    timeline['fetched_at'] = now()

def merge_txs(txs):
    rows = {t['event_id']: t for t in txs}
    return sorted(rows.values(), key=lambda t: (t.get('time_utc') or '', t['hash'], t['event_id']))

def missing(covered,lo,hi):
    intervals=[(lo,hi)]
    for left,right in sorted(covered):
        pieces=[]
        for a,b in intervals:
            if right<a or left>b:pieces.append((a,b));continue
            if a<left:pieces.append((a,left-1))
            if b>right:pieces.append((right+1,b))
        intervals=pieces
    return intervals
