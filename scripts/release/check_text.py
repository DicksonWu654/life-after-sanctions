#!/usr/bin/env python3
"""Print unresolved public-text matches only; successful output has zero lines."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from policy import ROOT,text_gate

if __name__=='__main__':
    _,failures=text_gate(ROOT)
    for failure in failures:print(json.dumps(failure,sort_keys=True))
    raise SystemExit(bool(failures))
