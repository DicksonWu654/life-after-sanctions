"""One reproducible record of completed acquisition and its bounded coverage.

A completed bounded snapshot can have known missing history. `complete` below
always means whole-address history; `acquisition_complete` means accounted-for
terminal source coverage, including documented unsupported/window-only scopes.
"""
import datetime as dt
import gzip
import json
from pathlib import Path
import re
from collections import defaultdict
from .pipeline_io import read_json, rows, digest, write_json

PATH='data/FETCH_STATUS.json'
EVM={'eth','arb','bsc','etc','polygon','base','op','avax'}

def prefix_metadata(path):
    """Read bounded top-level metadata from non-EVM collector JSON headers.

    Collector output puts coverage before txs. Never decompress a bulk array
    just to determine completion. Unknown layouts remain explicit unknowns.
    """
    opener=gzip.open if path.name.endswith('.gz') else open
    decoder=json.JSONDecoder();text=''
    with opener(path,'rt') as stream:
        for _ in range(128):
            chunk=stream.read(65536)
            if not chunk:break
            text+=chunk
            found={}
            for field in ('coverage','fetched_at'):
                m=re.search(r'"'+field+r'"\s*:',text)
                if m:
                    try:found[field]=decoder.raw_decode(text,m.end()+len(text[m.end():])-len(text[m.end():].lstrip()))[0]
                    except json.JSONDecodeError:pass
            if len(found)==2:return found
    return {'coverage':{},'metadata_error':'Collector metadata header unavailable'}

def build(root):
    root=Path(root);ledger=rows(root/'data/addresses.csv')
    report_ref='data/raw/evm/reports/coverage.json.gz'
    evm=read_json(root/report_ref,{})
    evm_rows={(r['chain'].lower(),r['address'].lower()):r for r in evm.get('rows',[])}
    invalid={(r['chain'].lower(),r['address'].lower()):r for r in evm.get('unqueryable_inputs',[])}
    evidence={report_ref:digest(root/report_ref)} if (root/report_ref).exists() else {}
    chains=defaultdict(list)
    for source in ledger:
        chain=source['chain'].lower();address=source.get('address_normalized') or source['address']
        address=address.lower() if address.startswith('0x') else address
        if chain in EVM:
            row=evm_rows.get((chain,address));bad=invalid.get((chain,address))
            complete=bool(row and row.get('complete'))
            accounted=bool(bad or row and (complete or row.get('pool') or chain in {'bsc','base'}))
            at=evm.get('generated_at');ref=report_ref
            scope='whole_history' if complete else 'pool_events_only' if row and row.get('pool') else 'unqueryable_input' if bad else 'partial_or_unavailable'
            limits=(row or {}).get('notes',[]) + ([bad['reason']] if bad else [])
        else:
            path=next((root/'data/timelines'/chain/(address+ext) for ext in ('.json.gz','.json') if (root/'data/timelines'/chain/(address+ext)).exists()),None)
            meta=prefix_metadata(path) if path else {};cov=meta.get('coverage',{})
            complete=cov.get('complete') is True;at=meta.get('fetched_at');ref=str(path.relative_to(root)) if path else 'data/addresses.csv'
            accounted=bool(cov) and not meta.get('metadata_error') and (complete or cov.get('priority_windows_complete') or cov.get('protected_windows_complete') or chain in {'bnb','sol','xmr','unknown','xvg','zec'})
            scope='whole_history' if complete else 'windows_only' if cov.get('priority_windows_complete') or cov.get('protected_windows_complete') else 'partial_or_unsupported'
            limits=cov.get('notes',[])
        row={'address':address,'complete':complete,'acquisition_complete':accounted,'scope':scope,'checked_at_utc':at,'raw_ref':ref}
        if not complete:row['limitations']=limits
        chains[chain].append(row)
    output=[]
    for chain,group in sorted(chains.items()):
        dates=sorted(r['checked_at_utc'] for r in group if r['checked_at_utc'])
        output.append({'chain':chain,'addresses':len(group),'complete':all(r['complete'] for r in group),
            'complete_histories':sum(r['complete'] for r in group),'acquisition_complete':all(r['acquisition_complete'] for r in group),
            'earliest_checked_at_utc':dates[0] if dates else None,'latest_checked_at_utc':dates[-1] if dates else None,
            'raw_ref':['data/addresses.csv']+sorted({r['raw_ref'] for r in group}),
            'exceptions':[r for r in group if not r['complete']]})
    state=read_json(root/'data/raw/freezes/state.json.gz',{})
    heads=state.get('published_heads',{})
    freeze_ref='data/raw/freezes/state.json.gz'
    if (root/freeze_ref).exists():evidence[freeze_ref]=digest(root/freeze_ref)
    return {'schema_version':1,'script':'scripts/lib/fetch_status.py',
        'acquisition_complete':all(r['acquisition_complete'] for r in output),
        'complete':all(r['complete'] for r in output),'chains':output,
        'issuer_history':{'complete':bool(heads) and not state.get('pending'),
            'checked_through_utc':{k:dt.datetime.fromtimestamp(v['timestamp_ms']/1000,dt.timezone.utc).isoformat().replace('+00:00','Z') for k,v in heads.items()},'raw_ref':freeze_ref},
        'evidence_sha256':evidence,'addresses_sha256':digest(root/'data/addresses.csv'),
        'meaning':'provisional describes unfinished acquisition for the stated bounded study; complete describes whole-address history. Terminal privacy/provider gaps and window-only histories stay explicit exceptions. Neither false provisional nor a completed acquisition implies complete population coverage.'}

def write(root):
    result=build(root);write_json(Path(root)/PATH,result);return result

def apply_status(result, root, analysis):
    root=Path(root);status=read_json(root/PATH,{})
    provisional=not status.get('acquisition_complete',False)
    if analysis=='freeze_match':provisional=not status.get('issuer_history',{}).get('complete',False)
    if analysis=='tornado':provisional=provisional or not result.get('coverage',{}).get('all_pools_events_complete',False) or bool(result.get('fetch_failures'))
    result['provisional']=provisional
    result['fetch_status']={'raw_ref':PATH,'sha256':digest(root/PATH) if (root/PATH).exists() else None,
        'meaning':status.get('meaning','Missing acquisition status; provisional.'),
        'acquisition_complete':status.get('acquisition_complete',False),
        'whole_history_complete_by_chain':{r['chain']:r['complete'] for r in status.get('chains',[])},
        'exceptions_ref':PATH+'#chains[].exceptions'}
    for case in result.get('cases',[]):case['provisional']=provisional
    def wording(value):
        if isinstance(value,dict):return {k:wording(v) for k,v in value.items()}
        if isinstance(value,list):return [wording(v) for v in value]
        if isinstance(value,str) and not provisional:
            return value.replace('All results are provisional while fetchers run.','Acquisition completed for the saved bounded study; coverage exceptions remain explicit.').replace('fetchers still active;','completed bounded acquisition;').replace('Shared fetchers are still running;','Bounded acquisition is complete;').replace('coverage is provisional.','coverage has documented limits.')
        return value
    return wording(result)

def report_status(text, result):
    if result.get('provisional',True):return text
    if isinstance(text,bytes):return report_status(text.decode('utf-8'),result).encode('utf-8')
    for old,new in (
        ('— provisional','— completed bounded snapshot'),
        ('`provisional:true`','`provisional:false`'),
        ('`provisional: true`','`provisional: false`'),
        ('fetchers are still running.','acquisition is complete for the bounded study; history exceptions remain.'),
        ('while shared fetchers continue running.','against the saved acquisition record.'),
        ('Eight cases are provisional.','Eight cases describe the completed bounded snapshot.'),
        ('Acquisition is still running.','Acquisition is complete for the bounded study; coverage limits remain.'),
        ('Provisional snapshot:','Completed bounded snapshot:'),
        ('This provisional snapshot is not yet a complete cross-chain population estimate.','This bounded snapshot is not a complete cross-chain population estimate.'),
    ):text=text.replace(old,new)
    return text
