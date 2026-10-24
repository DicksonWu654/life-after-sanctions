#!/usr/bin/env python3
"""Offline verification of the included publication; raw-payload checks need the full cache."""
from __future__ import annotations
import argparse
import csv
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from policy import ROOT, MAX_TREE, MAX_FILE, MAX_DERIVED, LABEL_SOURCES, load, sha, text_gate


def require(condition,message):
    if not condition:raise ValueError(message)


def findings():
    # Reuse the independent editorial decoder, locator, rounding and audit rules;
    # its raw-response checker is deliberately not invoked on the public cache.
    path=ROOT/'scripts/analysis/findings_check.py'
    spec=importlib.util.spec_from_file_location('editorial_rules',path)
    rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)
    results={str(p.relative_to(ROOT)):rules.decode(p.read_text()) for p in (ROOT/'results').glob('*.json')}
    audit=rules.independent_freeze_metrics()
    previous='';tags=audit_tags=examples=0
    sections=0;numeric_lines=set();tagged_lines=set();previous_index=None
    for number,line in enumerate((ROOT/'FINDINGS.md').read_text().splitlines(),1):
        if line.startswith('## ') and line!='## What we could not see':sections+=1
        match=rules.TAG.fullmatch(line) or rules.AUDIT_TAG.fullmatch(line)
        if ('<!-- check:' in line or '<!-- audit-check:' in line) and not match:
            raise ValueError(f'Malformed finding tag on line {number}')
        if match:
            filename,locator,literal=match.groups()
            if filename.startswith('results/'):
                actual=rules.resolve(results[filename],locator)
                parent=rules.resolve(results[filename],locator.rsplit('.',1)[0])
                tags+=1
            else:
                require(filename=='data/verify/freeze_verify.csv','Unexpected audit source')
                parent=audit[locator];actual=parent['value'];audit_tags+=1
            expected=rules.decode(literal)
            require(not isinstance(actual,bool) and isinstance(actual,(int,Decimal)),'Non-numeric finding tag')
            require(actual==expected,f'Finding tag drift on line {number}: {filename}#{locator}')
            require(rules.display_matches(previous,actual,parent.get('unit') if isinstance(parent,dict) else None),f'Visible finding rounding differs on line {number}')
            tagged_lines.add(previous_index)
        elif line.strip() and not line.startswith('<!--'):
            previous=line;previous_index=number
            if rules.numbers(line):numeric_lines.add(number)
        for tx in rules.TX.finditer(line):
            raw=rules.RAW.search(line)
            require(bool(raw),f'Missing raw identity for transaction example on line {number}')
            require(tx[2].lower().endswith(tx[1].lower()),f'Transaction/explorer mismatch on line {number}')
            examples+=1
    require(numeric_lines<=tagged_lines,'Untagged visible quantities in FINDINGS: '+str(sorted(numeric_lines-tagged_lines)))
    require(10<=sections<=15 and tags>0 and audit_tags==4,'Missing expected findings or independent audit tags')
    return {'findings':sections,'result_tags':tags,'independent_audit_tags':audit_tags,'transaction_links':examples,
            'raw_transaction_payloads_checked':False}


def site():
    meta=load(ROOT/'site/data/meta.json')
    require(meta.get('release_snapshot_date')=='2026-10-23','Unexpected snapshot date')
    require(not meta.get('fixture',False),'Fixture publication')
    for source in meta['analysis_sources'].values():
        require(sha(ROOT/source['path'])==source['sha256'],'Site result-source hash differs: '+source['path'])
    with (ROOT/'data/addresses.csv').open(newline='') as handle:rows=list(csv.DictReader(handle))
    addresses=load(ROOT/'site/data/addresses.json')
    require(len(addresses)==len(rows)==meta['counts']['addresses'],'Address population differs')
    details=list((ROOT/'site/data/address').glob('*/*.json'))
    require(len(details)==len(addresses),'Missing per-address publication files')
    ids={x['id'] for x in addresses}
    require(len(ids)==len(addresses),'Duplicate address IDs')
    detail_ids=set()
    for path in details:
        data=load(path)
        require(not data.get('fixture',False),'Fixture address detail')
        detail_ids.add(data['id'])
    require(detail_ids==ids,'Detail address IDs differ from the explorer index')
    for name in ('headline','cases','programs','sankey','freezes','cases_evidence','freezes_evidence'):
        load(ROOT/'site/data'/f'{name}.json')
    # Compare values directly to the editorial sources where cards quote a tag.
    cards=load(ROOT/'site/data/headline.json')
    require(all(x.get('finding_ref') and 'big' in x for x in cards),'Unreferenced site finding card')
    source_numbers={}
    def numerical_values(value):
        if isinstance(value,dict):
            for child in value.values():yield from numerical_values(child)
        elif isinstance(value,list):
            for child in value:yield from numerical_values(child)
        elif isinstance(value,(int,float)) and not isinstance(value,bool):
            yield Decimal(str(value))
    for card in cards:
        reference=card['finding_ref'].split('#',1)[0]
        require(reference.startswith('results/') and (ROOT/reference).is_file(),'Missing finding-card source')
        if reference not in source_numbers:
            source_numbers[reference]=set(numerical_values(load(ROOT/reference)))
        value=card['big'].get('value')
        if value is not None:
            require(Decimal(str(value)) in source_numbers[reference],'Site card quantity differs from its result source: '+card['id'])
    for path in (ROOT/'site').rglob('*'):
        if path.is_file():require(path.stat().st_size<=MAX_FILE,'Oversized site asset')
    html=(ROOT/'site/index.html').read_text()
    from html.parser import HTMLParser
    class Assets(HTMLParser):
        def __init__(self):super().__init__();self.assets=[]
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='script' and attrs.get('src'):self.assets.append(attrs['src'])
            if tag=='link' and attrs.get('rel')=='stylesheet':self.assets.append(attrs['href'])
    parser=Assets();parser.feed(html)
    for asset in parser.assets:
        if not asset.startswith(('https://','http://','data:')):
            require((ROOT/'site'/asset.split('?')[0]).is_file(),'Missing site asset: '+asset)
    return {'addresses':len(addresses),'detail_files':len(details),'finding_cards':len(cards),'cases':len(load(ROOT/'site/data/cases.json'))}


def licences():
    require((ROOT/'NOTICE').is_file(),'Missing third-party notice inventory')
    required_notices={
        'LICENSE-d3-sankey.txt':'Redistribution and use',
        'LICENSE-topojson-client.txt':'Permission to use',
        'LICENSE-iso-3166-1.txt':'Permission is hereby granted',
        'fonts/LICENSE-public-sans.txt':'SIL OPEN FONT LICENSE',
        'fonts/LICENSE-special-elite.txt':'Apache License',
        'fonts/NOTICE-special-elite.txt':'Brian J. Bonislawsky',
    }
    for relative,phrase in required_notices.items():
        require(phrase in (ROOT/'site/vendor'/relative).read_text(),'Missing upstream notice: '+relative)
    require({p.name for p in (ROOT/'data/prices').iterdir()}=={'manifest.csv'},'Third-party price payload included')
    counts={}
    for filename in ('labels.csv','labels_extra.csv'):
        import gzip
        path=ROOT/'data/labels'/filename
        if not path.exists():path=path.with_suffix(path.suffix+'.gz')
        opener=gzip.open if path.suffix=='.gz' else open
        with opener(path,'rt',newline='') as handle:
            rows=list(csv.DictReader(handle))
        require(all(x['source_id'] in LABEL_SOURCES for x in rows),'Restricted label source in '+filename)
        require(all(x['raw_ref'] or x['source_url'] for x in rows),'Label missing provenance')
        counts[filename]=len(rows)
    for source in load(ROOT/'data/labels/sources.json')['sources']:
        require(source['source_id'] in LABEL_SOURCES,'Restricted source manifest')
    def inspect_claims(value):
        if isinstance(value,list):
            for child in value:inspect_claims(child)
        elif isinstance(value,dict):
            if value.get('source_id') and ('label' in value or 'label_source' in value):
                require(value['source_id'] in LABEL_SOURCES,'Restricted nested label claim')
            for child in value.values():inspect_claims(child)
    for folder in ('results','site/data'):
        for path in (ROOT/folder).rglob('*.json'):inspect_claims(load(path))
    with gzip.open(ROOT/'data/derived/inflows.csv.gz','rt',newline='') as handle:
        for row in csv.DictReader(handle):inspect_claims(json.loads(row['sender_label_claims'] or '[]'))
    return counts


def request_index():
    import gzip
    by_ref={}
    with gzip.open(ROOT/'data/reference/raw_requests.jsonl.gz','rt') as handle:
        for line in handle:
            row=json.loads(line);by_ref[row['raw_ref']]=row
    require(all(row.get('request') or row.get('status')=='generated_artifact_or_source_blob' for row in by_ref.values()),'Unresolved raw request identity')
    raw_files=set(re.findall(r'\braw `([^`#]+)',(ROOT/'FINDINGS.md').read_text()))
    require(raw_files<=by_ref.keys(),'Missing finding request identities')
    missing=[ref for ref in raw_files if not by_ref[ref].get('request')]
    require(not missing,'Finding raw requests unavailable: '+str(missing))
    return {'indexed_references':len(by_ref),'finding_raw_requests':len(raw_files)}


def manifest():
    document=load(ROOT/'scripts/release/MANIFEST.json')
    records=document['files']
    total=0
    for relative,record in records.items():
        path=ROOT/relative
        require(path.is_file() and not path.is_symlink(),'Missing or linked publication file: '+relative)
        size=path.stat().st_size
        require(size==record['bytes'] and sha(path)==record['sha256'],'Manifest differs: '+relative)
        require(size<MAX_FILE,'File exceeds 50 MB: '+relative)
        if relative.startswith('data/derived/'):
            require(path.suffix=='.gz' and size<MAX_DERIVED,'Invalid derived publication file: '+relative)
        total+=size
    expected=set(records)|{'scripts/release/MANIFEST.json'}
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and not
            any(part in {'.git','.venv','__pycache__','build'} for part in p.relative_to(ROOT).parts)
            and p.suffix not in {'.pyc','.lock'}}
    require(actual==expected,'Unmanifested/missing files: '+str(sorted(actual^expected)[:20]))
    total+=(ROOT/'scripts/release/MANIFEST.json').stat().st_size
    require(total<MAX_TREE,'Tree exceeds 400 MB')
    for forbidden in ('data/raw','data/timelines','orches'+'tration','logs','site/screenshots','site/fixtures'):
        require(not (ROOT/forbidden).exists(),'Excluded directory included: '+forbidden)
    require(all(not any(part in {'AG'+'ENTS.md','BRIEF.md','HANDOFF.md','.env'} or part.endswith(('.sqlite','.sqlite3','.db')) for part in Path(relative).parts) for relative in actual),'Private file included')
    allowed,rejected=text_gate(ROOT)
    require(not rejected,'Unresolved public text matches: '+json.dumps(rejected[:8]))
    return {'files':len(expected),'bytes':total,'largest_file_bytes':max(x['bytes'] for x in records.values()),'unresolved_text_matches':0,'documented_text_exceptions':len(allowed)}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        report={'findings':findings(),'site':site(),'licences':licences(),'requests':request_index(),'manifest':manifest(),
            'full_cache_checks':'Not run: producer arithmetic and raw transaction payloads require omitted evidence and normalized histories.'}
        print(json.dumps({'status':'PASS',**report},indent=2))
    except (ValueError,OSError,KeyError) as exc:
        print('VERIFY FAILED: '+str(exc),file=sys.stderr);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
