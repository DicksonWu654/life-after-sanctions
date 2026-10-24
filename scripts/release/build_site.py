#!/usr/bin/env python3
"""Copy the verified saved publication to a self-contained static build/."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
DESTINATION=ROOT/'build'

def build():
    if DESTINATION.exists():shutil.rmtree(DESTINATION)
    DESTINATION.mkdir()
    for name in ('index.html','og.png','css','js','vendor','data'):
        source=ROOT/'site'/name;target=DESTINATION/name
        if source.is_dir():
            shutil.copytree(source,target,ignore=shutil.ignore_patterns('.*','*.lock','*.tmp'))
        else:shutil.copyfile(source,target)
    print('Static publication built in build/')

if __name__=='__main__':build()
