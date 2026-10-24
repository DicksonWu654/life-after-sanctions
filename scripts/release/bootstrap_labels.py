#!/usr/bin/env python3
"""Reacquire missing research label inputs before a refresh rebuild.

Network requests occur only when the refresh command invokes this helper.
Pinned source files are inert data, never installed or executed.
"""
from pathlib import Path
import gzip
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def bootstrap():
    manifest=json.loads((ROOT/'data/labels/sources.json').read_text())
    missing=any(not (ROOT/file['raw_ref'].split('#',1)[0]).is_file()
                for source in manifest['sources'] for file in source['files'])
    if missing:
        from scripts.labels.collect import collect
        collect(False)
    # Supplemental official claims refer to the exact original ledger snapshot,
    # rather than silently applying their row locators to a newer ledger.
    snapshot=ROOT/'data/reference/label_ledger_snapshot.csv.gz'
    target=ROOT/'data/raw/labels2/inputs/ledger.csv.gz'
    if snapshot.exists() and not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(snapshot.read_bytes())
    print('Research label cache is ready for rebuilding; public export reapplies licence filtering.')


if __name__=='__main__':bootstrap()
