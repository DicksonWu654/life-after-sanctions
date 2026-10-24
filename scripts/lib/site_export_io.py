"""Canonical site bytes and strict export replay comparisons.

Keep this separate from producer serialization: their saved hashes and schemas
must not change when the site's JSON formatting changes.
"""
import json
from .pipeline_io import atomic


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, separators=(',', ':'),
                       sort_keys=True, allow_nan=False)+'\n').encode()


def write_json(path, obj):
    atomic(path, json_bytes(obj))


def differing_fields(actual, expected, path='$', limit=8):
    """Report a bounded list of JSON paths; do not log bulky evidence values."""
    if type(actual) is not type(expected): return [path]
    if isinstance(actual, dict):
        found = []
        for key in sorted(actual.keys() | expected.keys()):
            child = path+'.'+key
            found += ([child] if key not in actual or key not in expected else
                      differing_fields(actual[key], expected[key], child, limit-len(found)))
            if len(found) >= limit: break
        return found
    if isinstance(actual, list):
        if len(actual) != len(expected): return [path]
        found = []
        for i, (a, b) in enumerate(zip(actual, expected)):
            found += differing_fields(a, b, f'{path}[{i}]', limit-len(found))
            if len(found) >= limit: break
        return found
    return [] if actual == expected else [path]


def compare_exports(published, reproduced):
    """Require every JSON byte, including recorded timestamps, to reproduce."""
    actual = {p.relative_to(published):p for p in published.rglob('*.json')}
    expected = {p.relative_to(reproduced):p for p in reproduced.rglob('*.json')}
    differences = []
    for rel in sorted(actual.keys() | expected.keys()):
        if rel not in actual or rel not in expected:
            differences.append(str(rel)+' (file set differs)')
            continue
        a, b = actual[rel].read_bytes(), expected[rel].read_bytes()
        if a == b: continue
        try: fields = differing_fields(json.loads(a), json.loads(b))
        except (ValueError, UnicodeError): fields = ['invalid JSON']
        differences.append(str(rel)+' ('+', '.join(fields or ['serialization bytes'])+')')
    if differences:
        raise RuntimeError('Export differs: '+', '.join(differences[:20]))
