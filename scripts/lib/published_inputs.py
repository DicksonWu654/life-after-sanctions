"""Retain the exact timeline cohort used by published analyses, despite live writers."""
from pathlib import Path
import os
import shutil
from .pipeline_io import ROOT, digest, read_json, utc, write_json

WORK = ROOT/'scripts/lib/.pipeline-work'
POINTER = WORK/'published-inputs.json'

def basis(root):
    paths=[root/'data'/f for f in ('ledger.csv','addresses.csv','actions.csv','freezes.csv','FETCH_STATUS.json')]
    paths += list((root/'data/prices').glob('*.csv*'))
    paths += [root/'data/labels'/f for f in ('labels.csv','labels.sqlite')]
    return {str(p.relative_to(root)):digest(p) for p in paths if p.is_file()}

def retain(gen):
    """Called only after a complete successful artifact publication."""
    WORK.mkdir(parents=True,exist_ok=True)
    folder = WORK/('inputs-'+gen.root.name)
    folder.mkdir()
    os.replace(gen.root/'data/timelines',folder/'timelines')
    timelines={str(p.relative_to(folder/'timelines')):digest(p) for p in (folder/'timelines').glob('*/*.json*')
               if p.name.endswith(('.json','.json.gz'))}
    info={'path':str(folder.relative_to(ROOT)),'created_at_utc':utc(),
          'timeline_sha256':timelines,'basis':basis(gen.root),
          'results':{str(p.relative_to(gen.root)):digest(p) for p in (gen.root/'results').glob('*.json')}}
    write_json(folder/'manifest.json',info)
    write_json(POINTER,{'path':info['path'],'manifest_sha256':digest(folder/'manifest.json')})
    return info

def current():
    """Replay only when current published results and non-timeline inputs match."""
    pointer=read_json(POINTER,{})
    if not pointer.get('path'): return None
    folder=(ROOT/pointer['path']).resolve()
    if not folder.is_relative_to(WORK.resolve()) or not folder.name.startswith('inputs-'):
        raise ValueError('Invalid published-input snapshot path')
    manifest=folder/'manifest.json'
    if not manifest.exists() or digest(manifest)!=pointer['manifest_sha256']:
        raise ValueError('Published-input snapshot manifest missing or changed; rebuild required')
    info=read_json(manifest)
    for rel,expected in (info['basis']|info['results']).items():
        path=ROOT/rel
        if not path.exists() or digest(path)!=expected: return None
    for rel,expected in info['timeline_sha256'].items():
        path=folder/'timelines'/rel
        if not path.exists() or digest(path)!=expected:
            raise ValueError('Published-input timeline snapshot changed: '+rel)
    return info

def public_info(info):
    if not info: return None
    return {'path':info['path'],'manifest_sha256':digest(ROOT/info['path']/'manifest.json'),
            'created_at_utc':info['created_at_utc'],'timelines':len(info['timeline_sha256'])}

def prune():
    """Keep the generation named by the published site and the active pointer."""
    keep={read_json(POINTER,{}).get('path'),(read_json(ROOT/'site/data/meta.json',{}).get('input_snapshot') or {}).get('path')}
    for folder in WORK.glob('inputs-*'):
        if str(folder.relative_to(ROOT)) not in keep: shutil.rmtree(folder)
