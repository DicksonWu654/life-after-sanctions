#!/usr/bin/env python3
"""Export a bounded, source-linked public snapshot. Performs no Git operations."""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import csv
import gzip
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tokenize
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import SITE_URL, SNAPSHOT_DATE
from policy import (ROOT, MAX_TREE, MAX_FILE, MAX_DERIVED, LABEL_SOURCES,
                    LICENCE_FILES, dump, load, sha, text_content, write_allowlist)

EXCLUDED_NAMES={'AG'+'ENTS.md','BRIEF.md','HANDOFF.md','.env','__pycache__',
    'COPY_REQUESTS.md','EXPORT_REQUESTS.md','TONE_CHANGES.json','VALIDATION.md',
    'findings-refresh.patch','propose_findings_refresh.py'}
SCRIPT_WORDS={
    'Co'+'dex: direct review of the 20 printed OFAC text excerpts in this task; no external human audit':'Computational review of 20 saved OFAC text excerpts; no external human audit',
    'orches'+'trator':'publication maintainer',
    'an ag'+'ent source-text review':'a computational source-text review',
    'another worker':'a concurrent process', 'other workers':'concurrent processes',
    "worker's":'process’s', 'worker’s':'process’s', 'Worker-owned':'Source',
    'this worker':'this collector', 'This worker':'This collector',
    'previous worker':'previous collection', 'Tornado worker':'Tornado analysis',
    'analysis worker':'analysis module', 'workers’':'processes’',
    'this job':'this analysis', 'This job':'This analysis',
    "job's":'analysis’s', 'job-specific':'analysis-specific',
    'completed job':'completed acquisition', 'fetch job':'collector',
    'coverage owner':'coverage documentation', 'ledger owner':'ledger maintainer',
    'owner-supplied':'supplied', 'owner-requested':'requested',
    "findings owner's":'findings', 'Owned outputs only':'Outputs',
    'Only the three assigned paths were edited.':'',
    'under owned paths':'in the source documentation',
    'cron safe':'safe for repeated invocation', 'cron retry':'refresh retry',
    'Other workers':'Concurrent processes', 'Other worker':'Concurrent process',
    'other worker':'concurrent process',
    'The tornado job owns':'The Tornado analysis covers',
    'This output hands over':'This output includes',
    'reserved for that job.':'covered by that separate analysis.',
    "No other live worker is accessible through this session's collaboration tools, so this file is the explicit coordination handoff.":'',
    'This process’s coverage notes live here because the job owns only its four assigned paths.':'Additional coverage notes are retained here.',
    'Job owns only cases.py, cases.json and CASES.md; case coverage is documented here and in CASES.md for the publication maintainer to append to docs/COVERAGE.md.':'Case-specific coverage is documented here and in CASES.md.',
    'append-ready for the coverage documentation':'source-specific',
    'Only the three owned outputs are retained;':'The analysis outputs are retained;',
    'only the three owned outputs':'the analysis outputs',
    'No Git commit.':'',
    '`docs/COVERAGE.md` is read-only to this analysis; the publication maintainer should append these ETH/TRX analysis gaps there.':'See `docs/COVERAGE.md` for the source-level summary.',
}


def public_prose(text):
    for before,after in SCRIPT_WORDS.items(): text=text.replace(before,after)
    return text


def source_script(text):
    """Remove optional home-directory credential fallback from exported collectors."""
    tree=ast.parse(text)
    lines=text.splitlines(keepends=True)
    remove=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.If): continue
        segment=ast.get_source_segment(text,node) or ''
        if 'Path.home()' in segment and 'ETHERSCAN_API_KEY' in segment and not node.orelse:
            # Pick the smallest conditional containing the home-directory read.
            children=[n for n in ast.walk(node) if isinstance(n,ast.If) and n is not node
                      and 'Path.home()' in (ast.get_source_segment(text,n) or '')]
            if not children: remove.append((node.lineno-1,node.end_lineno))
    for start,end in sorted(remove,reverse=True): del lines[start:end]
    result=public_prose(''.join(lines))
    ast.parse(result)
    return result


def include(path):
    rel=path.relative_to(ROOT)
    if any(p in EXCLUDED_NAMES or p.startswith('.') or p.endswith(('.sqlite','.sqlite3','.db','.pyc','.tmp')) for p in rel.parts):return False
    top=rel.parts[0]
    if top in {'README.md','LICENSE','NOTICE','CHANGELOG.md','FINDINGS.md'}:return True
    if top=='docs':return 'launch' not in rel.parts and path.suffix in {'.md','.py'}
    if top=='scripts':return path.suffix in {'.py','.json','.txt'}
    if top=='results':return path.suffix=='.json'
    if top=='site':
        return (rel.parts[1] in {'css','js','vendor','data'} or rel.name in {'index.html','og.png'})
    if top=='data':
        if len(rel.parts)==2:return rel.name in {'ledger.csv','addresses.csv','actions.csv','freezes.csv','FETCH_STATUS.json'}
        if rel.parts[1]=='prices':return rel.as_posix()=='data/prices/manifest.csv'
        return rel.parts[1] in {'reference','audit','verify'}
    return False


def restricted_claims(value):
    if isinstance(value,list):
        return [restricted_claims(x) for x in value if not (isinstance(x,dict) and x.get('source_id') and x['source_id'] not in LABEL_SOURCES)]
    if not isinstance(value,dict):return public_prose(value) if isinstance(value,str) else value
    out={}
    for k,v in value.items():
        if k in {'job','coverage_append_note'}:continue
        if k=='label_claims' and isinstance(v,list):
            out[k]=restricted_claims(v)
            continue
        out[k]=restricted_claims(v)
    if value.get('counterparty_label') and value.get('source_id') not in LABEL_SOURCES:
        out['counterparty_label']=None
        out['label_source']=None
    if value.get('label_claims') and not out.get('label_claims'):
        for k in ('label','entity_name','destination_label','counterparty_label'):
            if k in out:out[k]=None
        if 'examples' in out:
            for example in out['examples']:
                example.pop('destination_label',None)
        out['label_omitted']='Source lookup record omitted from public redistribution; aggregate research retains its original classification scope.'
    return out


def export_labels(dest):
    sources=load(ROOT/'data/labels/sources.json')
    report=[]
    for source in sources['sources']:
        sid=source['source_id'];keep=sid in LABEL_SOURCES
        if keep and sid in LICENCE_FILES:
            notice=ROOT/'data/labels/licenses'/LICENCE_FILES[sid]
            body=notice.read_text()
            assert ('Permission is hereby granted' in body if LABEL_SOURCES[sid]=='MIT' else 'Apache License' in body),sid
            target=dest/'data/labels/licenses'/notice.name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(notice,target)
        report.append({'source_id':sid,'license':source['license'],'included':keep,
            'reason':'Redistribution permission established from saved licence notice.' if keep and sid!='ofac' else
                     'Official US-government factual sanctions records.' if keep else
                     'BUSL terms are not a general open-data redistribution grant for this snapshot.' if sid=='across' else
                     'No explicit open-data redistribution permission established.'})
    dump(dest/'data/labels/sources.json',{**sources,'sources':[s for s in sources['sources'] if s['source_id'] in LABEL_SOURCES]})
    counts={}
    for filename in ('labels.csv','labels_extra.csv'):
        kept=Counter();dropped=Counter()
        with (ROOT/'data/labels'/filename).open(newline='') as handle:
            reader=csv.DictReader(handle)
            out=io.StringIO(newline='');writer=csv.DictWriter(out,reader.fieldnames);writer.writeheader()
            for row in reader:
                sid=row['source_id']
                if sid not in {x['source_id'] for x in report}:
                    report.append({'source_id':sid,'license':row['license'],'included':sid in LABEL_SOURCES,
                        'reason':'Official factual sanctions record.' if sid in LABEL_SOURCES else 'No explicit open-data redistribution permission established for the supplemental source.'})
                if sid not in LABEL_SOURCES:dropped[sid]+=1;continue
                kept[sid]+=1;writer.writerow(row)
        payload=out.getvalue().encode()
        target=dest/'data/labels'/(filename+'.gz' if len(payload)>MAX_DERIVED else filename)
        target.write_bytes(gzip.compress(payload,mtime=0) if target.suffix=='.gz' else payload)
        counts[filename]={'public_path':target.relative_to(dest).as_posix(),'included':sum(kept.values()),'omitted':sum(dropped.values()),'by_source':dict(kept),'omitted_by_source':dict(dropped)}
    dump(dest/'scripts/release/LABEL_LICENSES.json',{'sources':report,'tables':counts})
    return counts


def safe_request(value):
    if isinstance(value,dict):
        return {k:('[REDACTED]' if k.lower() in {'apikey','api_key','api-key','authorization','cookie','x-api-key'} else safe_request(v)) for k,v in value.items()}
    if isinstance(value,list):return [safe_request(v) for v in value]
    if isinstance(value,str):
        if value.startswith(('http://','https://')):
            parts=urlsplit(value)
            query=[(k,'[REDACTED]' if k.lower() in {'apikey','api_key','token','key'} else v) for k,v in parse_qsl(parts.query,keep_blank_values=True)]
            value=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),parts.fragment))
        return re.sub(r'(?i)((?:apikey|api_key|api-key|authorization)\s*[=:]\s*)[^&\s"\']+',r'\1[REDACTED]',value)
    return value


def raw_index(dest,cache=None):
    pattern=re.compile(r'data/raw/[A-Za-z0-9_.:/-]+?\.(?:(?:json|csv|txt|html|pdf)(?:\.gz)?|gz)')
    refs=set()
    cached={}
    if cache:
        with gzip.open(cache,'rt') as stream:
            for line in stream:
                row=json.loads(line)
                if row.get('request') or row.get('status')=='generated_artifact_or_source_blob':cached[row['raw_ref']]=row
    for path in dest.rglob('*'):
        if not path.is_file() or path.suffix not in {'.md','.json','.csv','.gz'}:continue
        content=text_content(path)
        if content:refs.update(pattern.findall(content))
    # Object blobs have sidecar request metadata; inspect that small metadata first.
    sidecars={}
    for folder in ('labels','labels2','priorart'):
        for path in (ROOT/'data/raw'/folder/'requests').glob('*.json'):
            try:
                j=load(path)
                if j.get('raw_ref'):sidecars[j['raw_ref']]=j
            except (OSError,ValueError):continue
    # Older collectors store metadata next to inert HTML/XML/PDF blobs.
    def remember(metadata):
        if not isinstance(metadata,dict):return
        url=metadata.get('url') or metadata.get('source_url')
        if metadata.get('raw_ref') and url:
            sidecars[metadata['raw_ref']]={**metadata,'request':{'method':'GET','url':url}}
            if metadata.get('text_ref'):
                sidecars[metadata['text_ref']]={**metadata,'request':{'method':'GET','url':url},'derived_from':metadata['raw_ref']}
        for value in metadata.values():
            if isinstance(value,dict):remember(value)
            elif isinstance(value,list):
                for item in value:remember(item)
    for path in (ROOT/'data/raw/audit').glob('*.json'):
        remember(load(path))
    if (ROOT/'data/raw/ofac/manifest.json').exists():remember(load(ROOT/'data/raw/ofac/manifest.json'))
    if (ROOT/'data/raw/ofac/fetches.jsonl').exists():
        with (ROOT/'data/raw/ofac/fetches.jsonl').open() as source:
            for line in source:remember(json.loads(line))
    prior_index=ROOT/'data/raw/priorart/source_index.csv'
    if prior_index.exists():
        with prior_index.open(newline='') as source:
            for row in csv.DictReader(source):remember(row)
    output=dest/'data/reference/raw_requests.jsonl.gz';output.parent.mkdir(parents=True,exist_ok=True)
    requests=artifacts=missing=0
    with output.open('wb') as handle,gzip.GzipFile(fileobj=handle,mode='wb',mtime=0,filename='') as stream:
        for ref in sorted(refs):
            path=ROOT/ref
            record={'raw_ref':ref}
            try:
                if ref in cached:
                    record=cached[ref]
                    if record.get('request'):requests+=1
                    else:artifacts+=1
                    stream.write((json.dumps(safe_request(record),sort_keys=True,separators=(',',':'))+'\n').encode())
                    continue
                metadata=sidecars.get(ref)
                if metadata is None:
                    opener=gzip.open if path.suffix=='.gz' else open
                    # Request headers precede response bodies in normal saved
                    # envelopes. Read a bounded prefix, rather than loading
                    # large histories merely to recover their request identity.
                    with opener(path,'rt',encoding='utf-8') as source:
                        prefix=source.read(262_144)
                    match=re.search(r'"request"\s*:\s*',prefix)
                    if match:
                        request,_=json.JSONDecoder().raw_decode(prefix[match.end():])
                        metadata={'request':request}
                    elif path.stat().st_size<262_144:
                        metadata=load(path)
                    else:
                        metadata={}
                request=metadata.get('request') if isinstance(metadata,dict) else None
                # Some sources save a request as a URL or JSON-RPC method/params.
                if request:
                    record['request']=safe_request(request);requests+=1
                    for k in ('retrieved_at','fetched_at','sha256','http_status','derived_from'):
                        if k in metadata:record[k]=metadata[k]
                else:
                    record['status']='generated_artifact_or_source_blob'
                    record['regenerate_with']='scripts/pipeline.py refresh; see source-specific collection and analysis scripts'
                    artifacts+=1
            except (OSError,ValueError,EOFError,UnicodeDecodeError):
                if path.is_file() and ref.endswith(('.csv','.csv.gz')):
                    record['status']='generated_artifact_or_source_blob'
                    record['regenerate_with']='Source-derived CSV; use the corresponding ledger, label or reference collector.'
                    artifacts+=1
                else:
                    record['status']='request_metadata_unavailable';missing+=1
            stream.write((json.dumps(record,sort_keys=True,separators=(',',':'))+'\n').encode())
            if (requests+artifacts+missing)%2000==0:print(f'Request index: {requests+artifacts+missing}/{len(refs)}',flush=True)
    return {'references':len(refs),'requests':requests,'generated_or_blob':artifacts,'unavailable':missing}


def derived_tables(dest):
    omitted=[]
    for path in sorted((ROOT/'data/derived').glob('*.csv*')):
        # Large edge tables cannot fit the release budget and stay reproducible via the pipeline.
        if path.stat().st_size>100_000_000:
            omitted.append({'path':str(path.relative_to(ROOT)),'reason':'Bulk calculation table excluded; regenerate from cache.'});continue
        target=dest/'data/derived'/(path.name if path.suffix=='.gz' else path.name+'.gz')
        target.parent.mkdir(parents=True,exist_ok=True)
        if path.suffix=='.gz':shutil.copyfile(path,target)
        elif path.name=='inflows.csv':
            # Do not redistribute restricted claims inside serialized CSV cells.
            with path.open(newline='') as source,target.open('wb') as raw_handle, \
                    gzip.GzipFile(fileobj=raw_handle,mode='wb',mtime=0,filename='') as compressed, \
                    io.TextIOWrapper(compressed,encoding='utf-8',newline='') as handle:
                reader=csv.DictReader(source);writer=csv.DictWriter(handle,reader.fieldnames);writer.writeheader()
                for row in reader:
                    claims=json.loads(row['sender_label_claims'] or '[]')
                    retained=restricted_claims(claims)
                    row['sender_label_claims']=json.dumps(retained,separators=(',',':'))
                    row['sender_label_raw_refs']=''
                    writer.writerow(row)
        else:
            with path.open('rb') as source,target.open('wb') as handle,gzip.GzipFile(fileobj=handle,mode='wb',mtime=0,filename='') as stream:
                shutil.copyfileobj(source,stream)
        if target.stat().st_size>=MAX_DERIVED:
            target.unlink();omitted.append({'path':str(path.relative_to(ROOT)),'reason':'Compressed size exceeds 20 MB release limit.'})
    return omitted


MAKEFILE='''PYTHON ?= .venv/bin/python
.PHONY: verify build serve refresh rebuild check export
verify:
\t$(PYTHON) -S -B scripts/release/verify_public.py
build: verify
\t$(PYTHON) -S -B scripts/release/build_site.py
serve:
\tpython3 -m http.server 8731 --bind 127.0.0.1 --directory site
refresh rebuild check export:
\t$(PYTHON) -S -B scripts/pipeline.py $@
'''


def export(destination,request_cache=None):
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Destination must be empty. Choose a fresh directory; existing files are never removed.')
    if destination.resolve()==ROOT or destination.resolve().is_relative_to(ROOT):
        raise ValueError('Export must be outside the source tree.')
    destination.mkdir(parents=True,exist_ok=True)
    report={'snapshot_date':SNAPSHOT_DATE,'omitted_derived':[],'source_files':{},'transformed':[]}
    for path in sorted(ROOT.rglob('*')):
        if path.is_symlink() or not path.is_file() or not include(path):continue
        rel=path.relative_to(ROOT);target=destination/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        before=sha(path)
        if rel.parts[0]=='scripts' and path.suffix=='.py' and rel.parts[1]!='release':
            source=source_script(path.read_text())
            if rel.as_posix()=='scripts/pipeline.py':
                marker='    new_addresses = addresses_set()-previous_addresses'
                bootstrap="""    # Cold public clones reacquire label inputs excluded from the snapshot.
    with Generation() as gen:
        prepare_outputs(gen,['data/raw/labels','data/raw/labels2','data/labels'])
        runner.required(gen,'labels-cache','scripts/release/bootstrap_labels.py',network=True)
        gen.publish()
"""
                if source.count(marker)!=1:raise ValueError('Pipeline refresh insertion point changed')
                source=source.replace(marker,bootstrap+marker)
                due_marker='    def due(name):\n'
                if source.count(due_marker)!=1:raise ValueError('Pipeline source-cooldown insertion point changed')
                source=source.replace(due_marker,due_marker+"        if not (ROOT/'data/raw'/('ofac' if name=='ledger' else name)).exists(): return True\n")
                ast.parse(source)
            target.write_text(source)
        elif rel.as_posix()=='site/og.png':
            preview=ROOT/'scripts/release/og.png'
            shutil.copyfile(preview if preview.exists() else path,target)
        elif path.suffix=='.json':
            value=restricted_claims(load(path))
            if rel.as_posix()=='results/premove.json':
                detail=value.pop('address_results')
                detail_ref='data/derived/premove_address_results.json.gz'
                dump(destination/detail_ref,detail)
                value['address_results_ref']=detail_ref
            dump(target,value)
        else:shutil.copyfile(path,target)
        if before!=sha(path):raise RuntimeError('Source changed during export: '+str(rel))
        report['source_files'][rel.as_posix()]=before
        if before!=sha(target):report['transformed'].append(rel.as_posix())
        if target.stat().st_size>MAX_FILE:raise ValueError('Oversized publication file: '+str(rel))
    from presentation import enrich
    enrich(ROOT,destination)
    report['price_series']='Omitted; data/prices/manifest.csv and scripts/prices/price.py retained.'
    report['labels']=export_labels(destination)
    report['omitted_derived']=derived_tables(destination)
    # Exact official-source snapshot needed by supplemental label row locators.
    label_snapshot=ROOT/'data/raw/labels2/inputs/ledger.csv.gz'
    if label_snapshot.exists():
        shutil.copyfile(label_snapshot,destination/'data/reference/label_ledger_snapshot.csv.gz')
    (destination/'Makefile').write_text(MAKEFILE)
    (destination/'requirements.txt').write_text('# Core pipeline and release checks use Python 3.11+ standard library only.\n')
    (destination/'.gitignore').write_text('''/.venv/
/build/
/logs/
/data/raw/
/data/timelines/
/scripts/lib/.pipeline-work/
__pycache__/
*.pyc
*.sqlite
*.sqlite3
*.db
*.lock
*.tmp
.env
.env.*
''')
    if SITE_URL.startswith('https://'):
        readme=destination/'README.md'
        readme.write_text(readme.read_text().replace('](site/)',']('+SITE_URL.rstrip('/')+'/)'))
    # Record both original source hashes and actual public-file hashes.
    meta=load(destination/'site/data/meta.json')
    for value in meta['analysis_sources'].values():
        value['original_sha256']=value['sha256']
        value['sha256']=sha(destination/value['path'])
    meta['release_snapshot_date']=SNAPSHOT_DATE
    dump(destination/'site/data/meta.json',meta)
    report['raw_request_index']=raw_index(destination,request_cache)
    drift=[rel for rel,before in report['source_files'].items() if sha(ROOT/rel)!=before]
    # Copy presentation assets last: source collection and text inspection can
    # take longer than a concurrent stylesheet edit. Scientific inputs and
    # executable release code must remain unchanged throughout construction.
    report['synchronized_assets']=[]
    for rel in drift[:]:
        asset=Path(rel)
        if asset.parts[0]=='site' and ('data' not in asset.parts) and asset.suffix in {'.html','.js','.css','.png','.woff2','.txt'}:
            before=sha(ROOT/rel)
            shutil.copyfile(ROOT/rel,destination/rel)
            if sha(ROOT/rel)!=before:raise RuntimeError('Presentation asset is still changing: '+rel)
            report['source_files'][rel]=before
            report['synchronized_assets'].append(rel)
            drift.remove(rel)
    if drift:raise RuntimeError('Source changed during release construction; export again: '+', '.join(drift))
    dump(destination/'scripts/release/EXPORT_REPORT.json',report)
    rejected=write_allowlist(destination)
    manifest={}
    for path in sorted(destination.rglob('*')):
        if path.is_file():
            rel=path.relative_to(destination).as_posix()
            manifest[rel]={'bytes':path.stat().st_size,'sha256':sha(path)}
    dump(destination/'scripts/release/MANIFEST.json',{'snapshot_date':SNAPSHOT_DATE,'files':manifest})
    total=sum(v['bytes'] for v in manifest.values())+(destination/'scripts/release/MANIFEST.json').stat().st_size
    for rel,record in manifest.items():print(f"{record['bytes']:>10}  {rel}")
    print(f'TOTAL {total:,} bytes; {len(manifest)+1} files; unresolved public-text matches: {len(rejected)}')
    if total>=MAX_TREE:raise ValueError('Release tree exceeds 400 MB')
    if rejected:
        for hit in rejected[:30]:print(json.dumps(hit))
        raise ValueError('Unresolved public-text matches; inspect the listed lines.')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=ROOT.parent/'life-after-sanctions-public')
    parser.add_argument('--request-index-cache',type=Path,help='Reuse redacted immutable request identities from a previous export')
    args=parser.parse_args()
    try:export(args.destination.expanduser(),args.request_index_cache)
    except (OSError,ValueError,RuntimeError) as exc:
        print('EXPORT FAILED: '+str(exc),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
