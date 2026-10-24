#!/usr/bin/env python3
"""Offline rebuild/check and bounded, transactional source refresh for the site."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
from decimal import Decimal, InvalidOperation
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lib.pipeline_io import ROOT, Generation, digest, read_json, rows, utc, write_json
from scripts.export_site import export, generation_clock
from scripts.lib import published_inputs
from scripts.lib import fetch_status

PYTHON = str(ROOT/'.venv/bin/python')
SCRIPTS = {'ledger':'scripts/ledger/build_ledger.py','prices':'scripts/prices/price.py',
           'freezes':'scripts/freezes/fetch_freezes.py','labels':'scripts/labels/build.py',
           'evm':'scripts/fetch/evm/fetch.py','utxo':'scripts/fetch/utxo/fetch.py',
           'tron':'scripts/fetch/tron/fetch.py','other':'scripts/fetch/other/fetch.py'}
CHAINS = {'evm':{'eth','arb','bsc','polygon','base','op','avax','etc'},
          'utxo':{'btc','bch','bsv','ltc','dash','doge','zec','btg','xvg','xmr'},
          'tron':{'trx'},'other':{'sol','xrp','xmr','bnb','unknown','unresolved_usdt'}}
PRINT_LOCK = threading.Lock()
SOURCE_STATUS_LOCK = threading.Lock()
REFRESH_PROTOCOL = 2
SECRET = re.compile(r'(?i)((?:apikey|api_key|api-key|authorization|secret|token)\s*[=:]\s*)[^&\s"\']+')

def redact(s): return SECRET.sub(r'\1[REDACTED]',s)

class Runner:
    def __init__(self, timeout=1800, log=None, network_timeout=3600):
        self.timeout, self.log, self.network_timeout = timeout, log, network_timeout
        self.results = []
    def say(self, text):
        text = redact(text)
        with PRINT_LOCK:
            print(text,flush=True)
            if self.log:
                with self.log.open('a') as f: f.write(text+'\n')
    def run(self, gen, name, script, flags=(), network=False, as_of_utc=None):
        cmd = [PYTHON,'-S','-B',str(gen.root/'scripts/lib/run_step.py'),str(gen.root),
               'network' if network else 'offline',script,*map(str,flags)]
        started = time.monotonic()
        self.say(f'[{utc()}] start {name}: {script} '+ ' '.join(map(str,flags)))
        # Each step owns its process group; timeout never signals a concurrent process.
        with tempfile_output() as output:
            env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            env.pop('LAS_CHECK_AS_OF_UTC',None)
            if as_of_utc: env['LAS_CHECK_AS_OF_UTC'] = as_of_utc
            proc = subprocess.Popen(cmd,cwd=gen.root,stdout=output,stderr=subprocess.STDOUT,
                                    start_new_session=True,env=env)
            timed_out = False
            try: code = proc.wait(timeout=self.network_timeout if network else self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid,signal.SIGTERM)
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL); proc.wait()
                code = 124
            output.seek(0)
            text = redact(output.read().decode('utf-8','replace'))
        result = {'name':name,'script':script,'flags':list(flags),'exit_code':code,'timed_out':timed_out,
                  'seconds':round(time.monotonic()-started,2),'finished_at_utc':utc()}
        if as_of_utc: result['as_of_utc'] = as_of_utc
        with PRINT_LOCK: self.results.append(result)
        if self.log:
            with PRINT_LOCK:
                with self.log.open('a') as f: f.write(f'--- {name} output ---\n'+text+'\n')
        self.say(f'[{utc()}] {name}: exit={code}, {result["seconds"]}s')
        if code:
            self.say('\n'.join(text.splitlines()[-12:]))
        result['output'] = text
        return result
    def required(self, *args, **kwargs):
        result = self.run(*args,**kwargs)
        if result['exit_code']: raise RuntimeError('Required step failed: '+result['name'])
        return result

class tempfile_output:
    def __enter__(self):
        import tempfile
        self.f = tempfile.TemporaryFile()
        return self.f
    def __exit__(self,*args): self.f.close()

def parallel(tasks, workers=4):
    errors, results = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task) for task in tasks]
        for future in as_completed(futures):
            try: results.append(future.result())
            except Exception as exc: errors.append(str(exc))
    if errors: raise RuntimeError('; '.join(errors))
    return results

def export_step(runner, **kwargs):
    """Bound the in-process exporter as well as subprocess-based steps."""
    started=time.monotonic()
    previous_handler=signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise TimeoutError(f'Export timed out after {runner.timeout:g} seconds')
    signal.signal(signal.SIGALRM,expired)
    previous_timer=signal.setitimer(signal.ITIMER_REAL,runner.timeout)
    runner.say(f'[{utc()}] start export'+(' check' if kwargs.get('check') else ''))
    try: return export(**kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL,max(.001,previous_timer[0]-(time.monotonic()-started)),previous_timer[1])
        runner.say(f'[{utc()}] export finished after {time.monotonic()-started:.2f}s')

def prepare_outputs(gen, rels):
    for rel in rels: gen.writable(rel)

def analysis_output_paths(stem):
    common = [f'results/{stem}.json',f'docs/analysis/{stem.upper()}.md']
    if stem=='flows': common += ['data/derived/flows_edges.csv','data/raw/flows']
    if stem=='inflows': common += ['data/derived/inflows.csv']
    if stem=='tornado': common += ['data/derived/tornado_daily.csv','data/raw/tornado']
    if stem=='checkpoints': common += ['data/derived/address_summary.csv']
    if stem=='freeze_match': common += ['data/derived/freeze_match.csv']
    return common

def prepare_analysis(gen, stem):
    for rel in analysis_output_paths(stem):
        if rel.startswith('data/derived/'):
            # Old bulk tables are not needed by a fresh calculation. Keep the
            # baseline for conflict detection without duplicating gigabytes.
            p = Path(rel)
            for parent in reversed(p.parents):
                if str(parent) != '.': gen.branch(parent)
            from scripts.lib.pipeline_io import signature
            gen.baseline[rel] = signature(ROOT/rel)
            target = gen.root/rel
            if target.is_symlink(): target.unlink()
            gen.writable_paths.append(p)
        else: gen.writable(rel)

def rebuild(runner, workers, publish_site=True):
    with Generation() as gen:
        gen.snapshot('data/timelines')
        prepare_outputs(gen,['data/ledger.csv','data/addresses.csv','data/actions.csv','docs/LEDGER.md'])
        runner.required(gen,'ledger',SCRIPTS['ledger'])
        prepare_outputs(gen,['data/raw/freezes','data/raw/prices','data/prices','data/labels',
                             'data/freezes.csv','docs/FREEZES.md','docs/COVERAGE.md'])
        parallel([lambda:runner.required(gen,'prices-check',SCRIPTS['prices'],['--check']),
                  lambda:runner.required(gen,'freezes',SCRIPTS['freezes'],['--pipeline-rebuild']),
                  lambda:runner.required(gen,'labels',SCRIPTS['labels'])],workers)
        gen.writable(fetch_status.PATH)
        status=fetch_status.write(gen.root)
        runner.say('Acquisition status: '+json.dumps({'complete':status['acquisition_complete'],'whole_history_complete':status['complete']}))
        analyses = sorted((gen.root/'scripts/analysis').glob('*.py'))
        independent = []
        for script in analyses:
            if script.stem in ('trace','cases','findings_check'): continue
            prepare_analysis(gen,script.stem)
            flags = ['--from-snapshot'] if script.stem=='tornado' and (ROOT/'data/raw/tornado/input_snapshot.json.gz').exists() else []
            # Tornado's saved input snapshot has a stable analysis-specific filename.
            if script.stem=='tornado':
                text=script.read_text()
                if re.search(r'^SNAPSHOT\s*=.*',text,re.M) and '"--from-snapshot"' in text:
                    # Inspect the actual saved location through the configured constant.
                    m=re.search(r'^SNAPSHOT\s*=\s*RAW\s*/\s*[\'"]([^\'"]+)',text,re.M)
                    if m and (ROOT/'data/raw/tornado'/m[1]).exists(): flags=['--from-snapshot']
            independent.append(lambda script=script,flags=flags:runner.required(gen,script.stem,str(script.relative_to(gen.root)),flags))
        parallel(independent,workers)
        if (ROOT/'scripts/analysis/trace.py').exists():
            runner.required(gen,'trace','scripts/analysis/trace.py')
            runner.required(gen,'flows-resume','scripts/analysis/flows.py',['--resume'])
        if (gen.root/'scripts/analysis/cases.py').exists():
            prepare_analysis(gen,'cases')
            runner.required(gen,'cases','scripts/analysis/cases.py')
        gen.publish()
        published_inputs.retain(gen)
    result = export_step(runner) if publish_site else {}
    runner.say('export: '+json.dumps(result,sort_keys=True))
    if publish_site: published_inputs.prune()
    return result

def source_paths(name):
    if name=='ledger': return ['data/raw/ofac','data/ledger.csv','data/addresses.csv','data/actions.csv','docs/LEDGER.md']
    if name=='prices': return ['data/raw/prices','data/prices']
    if name=='freezes': return ['data/raw/freezes','data/freezes.csv','docs/FREEZES.md','docs/COVERAGE.md']
    return ['data/raw/'+('other' if name=='other' else name)]

def source_error(result):
    text = result['output']
    real = re.search(r'Traceback.*(?:AssertionError|SyntaxError|ImportError|ModuleNotFoundError|NameError|TypeError|WRITE_OUTSIDE_GENERATION)',text,re.S)
    if real: return 'failure'
    if result['exit_code'] or re.search(r'"(?:error|failures)"\s*:\s*(?:"[^"\n]+"|\[\s*\{)',text): return 'stale'
    return None

def source_revision(name):
    folder=(ROOT/SCRIPTS[name]).parent
    files={str(p.relative_to(ROOT)):digest(p) for p in sorted(folder.glob('*.py'))}
    return hashlib.sha256(json.dumps({'files':files,'chains':sorted(CHAINS.get(name,()))},sort_keys=True).encode()).hexdigest()

def persist_source_status(name, status):
    status=dict(status,protocol_version=REFRESH_PROTOCOL)
    status.setdefault('collector_revision',source_revision(name))
    with SOURCE_STATUS_LOCK:
        meta=read_json(ROOT/'site/data/meta.json',{})
        statuses=meta.setdefault('source_status',{})
        statuses[name]=statuses.get(name,{})|status
        if status.get('stale'):meta['provisional']=True
        write_json(ROOT/'site/data/meta.json',meta)
    return status

def refresh_source(name, runner):
    try:status=_refresh_source(name,runner)
    except Exception:
        persist_source_status(name,{'stale':True,'last_attempt_utc':utc(),'reason':'Source implementation/publication failure; previous source generation retained'})
        raise
    return persist_source_status(name,status)

def _refresh_source(name, runner):
    with Generation() as gen:
        paths = source_paths(name)
        prepare_outputs(gen,paths)
        if name in CHAINS:
            for chain in sorted(CHAINS[name]):
                gen.writable('data/timelines/'+chain)
            # Every fetcher receives the current complete ledger-derived list.
            flags = ['--refresh','--addresses','data/addresses.csv']
            if name=='evm': flags += ['--no-cross-chain']
        else: flags = ['--fetch'] if name=='ledger' else ['--refresh']
        result = runner.run(gen,'refresh-'+name,SCRIPTS[name],flags,network=True)
        status = source_error(result)
        if status:
            if status=='failure': raise RuntimeError(name+' implementation failure; see refresh log')
            return {'stale':True,'last_attempt_utc':utc(),
                    'reason':'Source refresh timed out; previous outputs retained' if result['timed_out'] else 'Source refresh failed; previous outputs retained',
                    'exit_code':result['exit_code']}
        # Fetchers can report failures in their saved summary despite exit 0.
        report_path = {'evm':'data/raw/evm/reports/fetch_run.json.gz','tron':'data/raw/tron/run-summary.json.gz','other':'data/raw/other/run-summary.json.gz'}.get(name)
        report = read_json(gen.root/report_path,{}) if report_path else {}
        if report.get('failures'):
            return {'stale':True,'last_attempt_utc':utc(),'reason':'Source reported request failures; previous outputs retained'}
        # Successful retries/fallbacks remain in http_errors as audit evidence.
        # Freshness follows terminal failures and the completed saved tail.
        if name=='evm':
            validation=runner.run(gen,'refresh-evm-coverage','scripts/fetch/evm/validate.py')
            if validation['exit_code']:
                return {'stale':True,'last_attempt_utc':utc(),'reason':'Refreshed EVM coverage validation failed; previous outputs retained'}
        # Refuse a cohort or history regression even when the source exits 0.
        if name=='ledger' and len(rows(gen.root/'data/addresses.csv')) < len(rows(ROOT/'data/addresses.csv')):
            return {'stale':True,'last_attempt_utc':utc(),'reason':'Ledger address count decreased; manual review required; previous outputs retained'}
        if name in CHAINS:
            for chain in CHAINS[name]:
                for p in (gen.root/'data/timelines'/chain).glob('*.json*'):
                    previous = read_json(ROOT/p.relative_to(gen.root),{})
                    current = read_json(p,{})
                    if name=='tron' and (current.get('balance_errors') or any(s.get('error') for s in current.get('incremental_refresh',current.get('fetch_state',{})).values())):
                        return {'stale':True,'last_attempt_utc':utc(),'reason':'Tron refresh has unresolved balance/history errors; previous outputs retained'}
                    if name=='tron' and current.get('incremental_refresh') and not all(s.get('complete') for s in current['incremental_refresh'].values()):
                        return {'stale':True,'last_attempt_utc':utc(),'reason':'Tron incremental tail is incomplete; previous outputs retained'}
                    if previous and (len(current.get('txs',[])) < len(previous.get('txs',[])) or
                       previous.get('coverage',{}).get('complete') and not current.get('coverage',{}).get('complete')):
                        return {'stale':True,'last_attempt_utc':utc(),'reason':'Timeline coverage regression rejected; previous outputs retained'}
        gen.publish()
        return {'stale':False,'last_attempt_utc':utc(),'last_success_utc':utc(),'reason':None}

def addresses_set():
    return {(r['chain'],r['address_normalized']) for r in rows(ROOT/'data/addresses.csv')}

def freeze_set():
    return {(r['chain'],r['token'],r['tx_hash'],r['log_index']) for r in rows(ROOT/'data/freezes.csv')}

def timeline_digests():
    return {str(p.relative_to(ROOT)):digest(p) for p in (ROOT/'data/timelines').glob('*/*.json*') if p.name.endswith(('.json','.json.gz'))}

def rebuild_fingerprint():
    paths = [ROOT/'data'/name for name in ('addresses.csv','ledger.csv','actions.csv','freezes.csv','FETCH_STATUS.json')]
    paths += list((ROOT/'data/prices').glob('*'))
    paths += list((ROOT/'data/labels').glob('labels.*'))
    paths += [p for p in (ROOT/'data/timelines').glob('*/*.json*') if p.name.endswith(('.json','.json.gz'))]
    paths += [p for p in (ROOT/'scripts').rglob('*.py') if '.pipeline-work' not in p.parts]
    return {str(p.relative_to(ROOT)):digest(p) for p in paths if p.is_file()}

def refresh(runner, args):
    meta = read_json(ROOT/'site/data/meta.json',{})
    statuses = meta.get('source_status',{})
    previous_addresses, previous_freezes, previous_timelines = addresses_set(), freeze_set(), timeline_digests()
    original_inputs = rebuild_fingerprint()
    # Same cohort + recent attempt is a deliberate refresh retry cooldown. New
    # addresses invalidate all chain-source cooldowns before fetchers run.
    def due(name):
        if not (ROOT/'data/raw'/('ofac' if name=='ledger' else name)).exists(): return True
        status=statuses.get(name,{})
        if status.get('protocol_version')!=REFRESH_PROTOCOL or status.get('collector_revision')!=source_revision(name): return True
        stamp = status.get('last_attempt_utc')
        if args.force or not stamp: return True
        age = (dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))).total_seconds()
        return age >= args.max_age_hours*3600
    did_work = False
    if due('ledger'):
        statuses['ledger'] = statuses.get('ledger',{}) | refresh_source('ledger',runner)
        statuses['ledger'].update(protocol_version=REFRESH_PROTOCOL,script_sha256=digest(ROOT/SCRIPTS['ledger']))
        did_work = True
    # Cold public clones reacquire label inputs excluded from the snapshot.
    with Generation() as gen:
        prepare_outputs(gen,['data/raw/labels','data/raw/labels2','data/labels'])
        runner.required(gen,'labels-cache','scripts/release/bootstrap_labels.py',network=True)
        gen.publish()
    new_addresses = addresses_set()-previous_addresses
    names = ['freezes','prices','evm','utxo','tron','other']
    selected = [name for name in names if due(name) or new_addresses and name in CHAINS]
    # Copying UTXO raw evidence costs ~2 GB. Limit concurrent stages to 2 by
    # default, stay below the project's 10 GB total scratch+data budget.
    # Freeze and EVM collectors share the same free-tier Etherscan key.
    # Serial source stages avoid combining their independent rate limiters.
    source_workers = 1
    with ThreadPoolExecutor(max_workers=source_workers) as pool:
        jobs = {pool.submit(refresh_source,name,runner):name for name in selected}
        for future in as_completed(jobs):
            name = jobs[future]
            statuses[name] = statuses.get(name,{}) | future.result()
            statuses[name].update(protocol_version=REFRESH_PROTOCOL,script_sha256=digest(ROOT/SCRIPTS[name]))
            did_work = True
    # Persist source status before analysis so a failed analysis cannot conceal
    # a source failure. Preserve the prior successful refresh stamp.
    # Source statuses are persisted on completion; read them again so a source
    # recovery begun before this invocation is not overwritten by its old view.
    statuses = read_json(ROOT/'site/data/meta.json',{}).get('source_status',statuses)
    meta['source_status'] = statuses
    write_json(ROOT/'site/data/meta.json',meta)
    fetch_status.write(ROOT)
    inputs_changed = rebuild_fingerprint() != original_inputs
    expected_analyses = {p.stem for p in (ROOT/'scripts/analysis').glob('*.py') if p.stem not in ('trace','findings_check')}
    # A prior interrupted refresh may already have published successful sources.
    # Cooldown is not evidence that the analyses describe those current inputs.
    needs_rebuild = inputs_changed or published_inputs.current() is None or bool(expected_analyses-set(meta.get('analysis_sources',{})))
    needs_export = needs_rebuild or not meta.get('export_counts')
    if needs_rebuild:
        rebuild(runner,args.workers,publish_site=False)
    elif did_work:
        runner.say('Rebuild inputs unchanged; retaining the published offline generation')
    if needs_export:
        result = export_step(runner,source_status=statuses)
    else:
        result = {'addresses':len(previous_addresses),'files_rewritten':0}
    finished = utc()
    completed_meta = read_json(ROOT/'site/data/meta.json',{})
    completed_meta.update(last_refreshed_utc=finished,source_status=statuses)
    for coverage in completed_meta.get('coverage',[]):
        status = statuses.get(coverage.get('source'),{})
        coverage['stale'] = status.get('stale',True)
        required_sources=[coverage.get('source'),'ledger','prices']+(['freezes'] if coverage.get('chain') in ('eth','trx') else [])
        coverage['stale_sources']=sorted(s for s in required_sources if statuses.get(s,{}).get('stale',True))
        base = f"{coverage.get('readable_histories',0)} saved histories; {coverage.get('complete_histories',0)} marked complete by provider. "
        coverage['notes'] = base + ('Source refresh stale: '+status.get('reason','not refreshed') if coverage['stale'] else 'See per-address coverage for asset and history limits.')
    write_json(ROOT/'site/data/meta.json',completed_meta)
    published_inputs.prune()
    current_timelines = timeline_digests()
    updated = sum(previous_timelines.get(p)!=sha for p,sha in current_timelines.items())
    message = f'refreshed at {finished}, {len(addresses_set()-previous_addresses)} new addresses, {len(freeze_set()-previous_freezes)} new freeze events, {updated} timelines updated'
    runner.say(message)
    return dict(result,summary=message,source_status=statuses,near_noop=not (did_work or needs_rebuild or needs_export))

TAG = re.compile(r'<!--\s*check:\s*(results/[\w./-]+\.json)#([^>]+?)\s*-->')
NUM = re.compile(r'(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?\s*%?')

def json_path(obj,path):
    if path.startswith('/'):
        pieces = [p.replace('~1','/').replace('~0','~') for p in path.split('/')[1:]]
    else:
        pieces = [p for p in re.split(r'\.|\[|\]',path.removeprefix('$.').removeprefix('$')) if p]
    for p in pieces: obj = obj[int(p)] if isinstance(obj,list) else obj[p]
    return obj

def findings_check(path=ROOT/'FINDINGS.md'):
    if not path.exists(): return {'file':str(path),'tagged_values':0,'note':'FINDINGS.md does not exist yet'}
    checked, errors, previous_prose = 0, [], ''
    for line_number,line in enumerate(path.read_text().splitlines(),1):
        tags = list(TAG.finditer(line))
        if '<!-- check:' in line and not tags:
            errors.append(f'{path.name}:{line_number}: malformed check annotation')
        for tag in tags:
            try:
                result_path = (ROOT/tag[1]).resolve()
                if not result_path.is_relative_to(ROOT/'results'): raise ValueError('Result path outside results')
                target, separator, explicit = tag[2].strip().partition(' = ')
                source = read_json(result_path)
                expected = json_path(source,target)
                unit = expected.get('unit') if isinstance(expected,dict) else None
                if unit is None and '.' in target:
                    parent=json_path(source,target.rsplit('.',1)[0])
                    if isinstance(parent,dict): unit=parent.get('unit')
                if isinstance(expected,dict): expected = expected['value']
                if isinstance(expected,bool) or not isinstance(expected,(int,float)) or not math_finite(expected):
                    raise ValueError('Check target is not a finite number')
                if separator and Decimal(str(expected))!=Decimal(explicit.strip()):
                    raise ValueError(f'saved number {expected} differs from explicit tag value {explicit}')
                # Associate this annotation with the immediately preceding
                # clause, allowing multiple independently tagged values/line.
                prior = max([m.end() for m in tags if m.end() <= tag.start()] or [0])
                clause = re.sub(r'\[[^\]]*\]\([^)]*\)',lambda m:m[0].split('](')[0][1:],line[prior:tag.start()])
                if not clause.strip(): clause=previous_prose
                clause = re.sub(r'^\s*(?:\d+[.)]\s+|[-*]\s+|#{1,6}\s+)','',clause)
                clause = re.sub(r'\b0x[0-9a-fA-F]+\b','',clause)
                tokens = list(NUM.finditer(clause))
                matched = False
                for token in tokens:
                    text = token[0].strip().replace(',','').replace('−','-')
                    percent = text.endswith('%')
                    literal = text.rstrip('%').strip()
                    actual = Decimal(str(expected)) * (100 if percent and unit in (None,'share') else 1)
                    suffix = re.match(r'^\s*(thousand|million|billion|trillion|bn|tn|[kmbt])\b',clause[token.end():],re.I)
                    if suffix:
                        factor = {'k':3,'thousand':3,'m':6,'million':6,'b':9,'bn':9,'billion':9,'t':12,'tn':12,'trillion':12}[suffix[1].lower()]
                        actual /= Decimal(10)**factor
                    # Decimal places express the published rounding precision;
                    # integer publication is exact (no rounded count drift).
                    if '.' in literal or 'e' in literal.lower():
                        from decimal import ROUND_HALF_UP
                        candidate = Decimal(literal)
                        matched |= actual.quantize(Decimal(1).scaleb(candidate.as_tuple().exponent),rounding=ROUND_HALF_UP)==candidate
                    else: matched |= actual == Decimal(literal)
                if not matched: raise ValueError(f'cited number does not match {expected} {unit or ""}')
                checked += 1
            except (KeyError,IndexError,TypeError,ValueError,InvalidOperation,FileNotFoundError) as exc:
                errors.append(f'{path.name}:{line_number}: {tag[1]}#{tag[2]}: {exc}')
        if line.strip() and not line.lstrip().startswith('<!--'):
            previous_prose = TAG.sub('',line).strip() or previous_prose
    if errors: raise RuntimeError('\n'.join(errors))
    return {'file':str(path),'tagged_values':checked}

def math_finite(x):
    import math
    return math.isfinite(x)

def restore_input_hashes(body, entry):
    """Recover exact published bytes using only declared input SHA-256 fields."""
    if hashlib.sha256(body).hexdigest() != entry['refreshed_sha256']:
        raise ValueError('Input-hash refresh result digest mismatch')
    expected = json.loads(body)
    restored = body
    for patch in entry['patches']:
        path = patch['path']
        allowed = (path==['preregistration_sha256'] or
                   len(path)==2 and path[0] in ('input_hashes','input_sha256') or
                   len(path)==3 and path[0]=='input_manifest' and isinstance(path[1],int) and path[2]=='sha256')
        if not allowed or not all(re.fullmatch('[0-9a-f]{64}',patch[k]) for k in ('published','refreshed')):
            raise ValueError('Refresh manifest may patch only input SHA-256 fields')
        parent = expected
        for key in path[:-1]: parent = parent[key]
        if parent[path[-1]] != patch['refreshed']:
            raise ValueError('Refreshed input hash does not match declared JSON path')
        parent[path[-1]] = patch['published']
        old, new = (json.dumps(patch[k]).encode() for k in ('refreshed','published'))
        if restored.count(old) != 1:
            raise ValueError('Ambiguous input hash replacement')
        restored = restored.replace(old,new,1)
    if json.loads(restored) != expected or hashlib.sha256(restored).hexdigest() != entry['published_sha256']:
        raise ValueError('Published result bytes were not recovered exactly')
    return restored


def check_snapshot():
    """Check current producers, then replay exact published export provenance.

    A copy-only input-hash refresh leaves site/data immutable. Its manifest
    records reversible SHA-256 edits, not alternative research values. Every
    current producer still runs --check. Only the export's staging copy uses
    recovered published bytes, whose complete digest must match both the frozen
    acquisition manifest and the published site. Export comparisons stay exact.
    """
    snapshot = published_inputs.current()
    if snapshot: return snapshot, {}
    refresh = read_json(ROOT/'docs/analysis/INPUT_HASH_REFRESH.json',{})
    public = read_json(ROOT/'site/data/meta.json',{}).get('input_snapshot')
    if not public or refresh.get('published_snapshot') != public: return None, {}
    pointer = read_json(published_inputs.POINTER,{})
    if pointer != {k:public[k] for k in ('path','manifest_sha256')}: return None, {}
    folder = (ROOT/public['path']).resolve()
    if not folder.is_relative_to(published_inputs.WORK.resolve()) or not folder.name.startswith('inputs-'):
        raise ValueError('Invalid input-hash refresh snapshot path')
    if digest(folder/'manifest.json') != public['manifest_sha256']:
        raise ValueError('Published acquisition manifest changed')
    snapshot = read_json(folder/'manifest.json')
    for rel, expected in snapshot['basis'].items():
        if digest(ROOT/rel) != expected:
            raise ValueError('Published non-timeline input changed: '+rel)
    for rel, expected in snapshot['timeline_sha256'].items():
        if digest(folder/'timelines'/rel) != expected:
            raise ValueError('Published timeline changed: '+rel)
    sources = read_json(ROOT/'site/data/meta.json',{})['analysis_sources']
    replay = {}
    for rel, expected in snapshot['results'].items():
        if sources[Path(rel).stem]['sha256'] != expected:
            raise ValueError('Site result provenance differs from acquisition manifest: '+rel)
        body = (ROOT/rel).read_bytes()
        if hashlib.sha256(body).hexdigest() == expected: continue
        entry = refresh['results'][rel]
        if entry['published_sha256'] != expected:
            raise ValueError('Refresh baseline differs from published result: '+rel)
        replay[rel] = restore_input_hashes(body,entry)
    if set(replay) != set(refresh['results']):
        raise ValueError('Input-hash refresh result set differs')
    return snapshot, replay


def check(runner,args):
    if read_json(ROOT/fetch_status.PATH,{}) != fetch_status.build(ROOT):
        raise RuntimeError('FETCH_STATUS differs from saved fetcher coverage; rebuild required')
    snapshot, export_replay = check_snapshot()
    reference,_=generation_clock(ROOT,snapshot)
    findings_path=Path(args.findings)
    editorial=findings_path.read_text() if findings_path.exists() else ''
    editorial_tags=list(TAG.finditer(editorial))
    native_editorial=bool(editorial_tags) and all(' = ' in t[2] for t in editorial_tags)
    with Generation() as gen:
        gen.snapshot('data/timelines',ROOT/snapshot['path']/'timelines' if snapshot else None)
        # Editorial provenance checks resolve references and reject symlinks
        # outside their generation. Materialize raw/result trees with COW links.
        for rel in ['data/raw','results','data/prices','data/labels',
                    'data/FETCH_STATUS.json',
                    'data/derived/address_summary.csv',
                    'data/ledger.csv','data/addresses.csv','data/actions.csv','data/freezes.csv']:
            gen.writable(rel)
        targets = [(name,script) for name,script in SCRIPTS.items() if name in ('ledger','prices','freezes','labels','evm','utxo')]
        targets += [(p.stem,str(p.relative_to(ROOT))) for p in sorted((ROOT/'scripts/analysis').glob('*.py'))
                    if p.stem!='findings_check' or native_editorial]
        # Other/Tron fetchers have no --check flag. Their offline validators are
        # included explicitly and the interface requests are documented.
        targets += [('tron-validate','scripts/fetch/tron/validate.py')]
        # Run every available check and retain every failure, rather than stop
        # at the first failed source.
        results = parallel([lambda name=name,script=script:runner.run(gen,'check-'+name,script,
                            ['--addresses','data/addresses.csv'] if name=='tron-validate' else
                            ['--check','--findings',str(findings_path)] if name=='findings_check' else ['--check'],
                            as_of_utc=reference.isoformat() if name=='prices' and reference else None)
                            for name,script in targets],args.workers)
        failures = [r['name'] for r in results if r['exit_code']]
        findings = {}
        try: findings = findings_check(findings_path)
        except Exception as exc: failures.append('FINDINGS: '+str(exc))
        # Producer checks above use refreshed results. The immutable published
        # export must reproduce its original, cryptographically verified bytes.
        if export_replay:
            runner.say(f'Export provenance: recovered exact published bytes for {len(export_replay)} input-hash-only result refreshes')
        for rel, body in export_replay.items(): (gen.root/rel).write_bytes(body)
        try: export_step(runner,root=gen.root,check=True,input_snapshot=snapshot)
        except Exception as exc: failures.append('export: '+str(exc))
    if failures: raise RuntimeError('Checks failed: '+'; '.join(failures))
    runner.say('All checks passed; '+str(findings['tagged_values'])+' FINDINGS.md values verified')
    return findings

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['rebuild','refresh','check','export'])
    parser.add_argument('--timeout',type=float,default=1800,help='Per-step timeout in seconds')
    parser.add_argument('--network-timeout',type=float,default=3600,help='Per network-source step timeout in seconds')
    parser.add_argument('--workers',type=int,default=3,help='Independent offline steps; network sources run sequentially')
    parser.add_argument('--max-age-hours',type=float,default=24,help='Cooldown between source attempts; new addresses bypass chain cooldown')
    parser.add_argument('--force',action='store_true',help='Refresh even during source cooldown')
    parser.add_argument('--findings',type=Path,default=ROOT/'FINDINGS.md',help='Editorial file to verify; defaults to the published FINDINGS.md')
    args = parser.parse_args()
    if args.timeout <= 0 or args.network_timeout <= 0 or args.workers < 1 or args.max_age_hours < 0: parser.error('Invalid limit')
    (ROOT/'site/data').mkdir(parents=True,exist_ok=True)
    lock = (ROOT/'site/data/.pipeline.lock').open('a')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('Another pipeline run holds the lock; exiting without changes',flush=True)
        return 0
    log = None
    if args.command=='refresh':
        (ROOT/'logs').mkdir(exist_ok=True)
        log = ROOT/'logs'/('refresh-'+dt.datetime.now(dt.timezone.utc).date().isoformat()+'.log')
    runner = Runner(args.timeout,log,args.network_timeout)
    try:
        if args.command=='rebuild': result = rebuild(runner,args.workers)
        elif args.command=='refresh': result = refresh(runner,args)
        elif args.command=='check': result = check(runner,args)
        else: result = export_step(runner)
        runner.say(json.dumps({'command':args.command,'status':'ok','result':result},sort_keys=True))
        return 0
    except Exception as exc:
        runner.say('FAILED: '+str(exc))
        return 1
    finally: lock.close()

if __name__=='__main__': raise SystemExit(main())
