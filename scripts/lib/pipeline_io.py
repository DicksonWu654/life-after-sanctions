"""Standard-library I/O and isolated working generations for the pipeline."""
from __future__ import annotations
import csv
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def read_json(path, default=None):
    path = Path(path)
    if not path.exists(): return default
    with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as f:
        return json.load(f)

def rows(path):
    csv.field_size_limit(100 * 1024 * 1024)
    path = Path(path)
    if not path.exists(): return []
    with (gzip.open(path, 'rt', newline='') if path.suffix == '.gz' else path.open(newline='')) as f:
        return list(csv.DictReader(f))

def atomic(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()

def write_json(path, obj):
    atomic(path, json_bytes(obj))

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def signature(path):
    try:
        s = path.stat()
        return (s.st_size, s.st_mtime_ns, s.st_ino)
    except FileNotFoundError:
        return None

def atomic_copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + dst.name + '.', dir=dst.parent)
    os.close(fd)
    try:
        shutil.copyfile(src, name)
        os.replace(name, dst)
    finally:
        Path(name).unlink(missing_ok=True)

def atomic_publish(src, dst):
    """Publish an immutable staged file without a third bulk copy on disk.

    Generations never modify their files after publication. Child writes to
    future COW generations still detach shared inodes in run_step.py.
    """
    if src.stat().st_size <= 20_000_000:
        return atomic_copy(src,dst)
    dst.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+dst.name+'.',dir=dst.parent)
    os.close(fd)
    try:
        Path(name).unlink()
        try:os.link(src,name)
        except OSError:shutil.copyfile(src,name)
        os.replace(name,dst)
    finally:Path(name).unlink(missing_ok=True)

class Generation:
    """Copies writable namespaces; all other inputs are linked, never promoted.

    Scripts are copied because their ROOT is derived from __file__. Publication
    checks the original stat before replacing a changed file, so concurrent
    workers' updates are not silently overwritten. A rejected source is discarded.
    """
    def __init__(self, root=ROOT):
        self.origin = Path(root)
        # Stay on the project's filesystem so immutable timeline snapshots can
        # use hardlinks instead of a second gigabyte of bulk evidence.
        scratch = self.origin / 'scripts/lib/.pipeline-work'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='generation-', dir=scratch)
        self.root = Path(self.temp.name)
        self.baseline = {}
        self.writable_paths = []
        shutil.copytree(self.origin / 'scripts', self.root / 'scripts', ignore=shutil.ignore_patterns('__pycache__','.pipeline-work'))
        for folder in ('data', 'results', 'docs'):
            dest = self.root / folder
            dest.mkdir()
            if (self.origin / folder).exists():
                for p in (self.origin / folder).iterdir():
                    (dest / p.name).symlink_to(p, target_is_directory=p.is_dir())
        (self.root / 'site').mkdir()
        (self.root / 'site/data').symlink_to(self.origin / 'site/data', target_is_directory=True)
        for name in ('BRIEF.md', 'FINDINGS.md'):
            if (self.origin / name).exists(): (self.root / name).symlink_to(self.origin / name)

    def snapshot(self, rel, source=None):
        """Pin atomic-writer inputs using hardlinks, without copying bulk data."""
        rel = Path(rel)
        for parent in reversed(rel.parents):
            if str(parent) != '.': self.branch(parent)
        dst, src = self.root / rel, Path(source) if source is not None else self.origin / rel
        if dst.is_symlink(): dst.unlink()
        def link_or_copy(source, target):
            try: os.link(source, target)
            except OSError: shutil.copy2(source, target)
        def ignored(directory,names):
            return [name for name in names if not (Path(directory)/name).is_dir() and not name.endswith(('.json','.json.gz'))]
        if src.exists(): shutil.copytree(src, dst, copy_function=link_or_copy,ignore=ignored)
        else: dst.mkdir(parents=True, exist_ok=True)

    def branch(self, rel):
        p = self.root / rel
        if p.is_symlink():
            target = p.resolve()
            p.unlink()
            p.mkdir()
            for child in target.iterdir():
                (p / child.name).symlink_to(child, target_is_directory=child.is_dir())
        elif not p.exists(): p.mkdir(parents=True)

    def writable(self, rel):
        rel = Path(rel)
        if rel.is_absolute() or not rel.parts or '..' in rel.parts:
            raise ValueError('Writable namespace must be relative to the generation')
        for parent in reversed(rel.parents):
            if str(parent) != '.': self.branch(parent)
        src, dst = self.origin / rel, self.root / rel
        if not dst.parent.resolve().is_relative_to(self.root.resolve()):
            raise ValueError('Writable namespace parent is outside the generation')
        if dst.is_symlink(): dst.unlink()
        candidates = list(src.rglob('*')) if src.is_dir() else [src]
        for p in candidates:
            if p.is_file(): self.baseline[str(p.relative_to(self.origin))] = signature(p)
        if src.is_dir():
            # Top-level namespaces already contain links created by __init__.
            # Copying over those links follows them back to the originals.
            # Replace only this generation's directory with a fresh clone.
            if dst.exists(): shutil.rmtree(dst)
            def link_or_copy(source, target):
                try: os.link(source,target)
                except OSError: shutil.copy2(source,target)
            # Raw caches and JSON timelines use reviewed Python file opens or
            # atomic replacements. The child guard breaks a hardlink before
            # an in-place write. Keep SQLite and other outputs as real copies.
            cow = rel.parts[:2] in (('data','raw'),('data','timelines'))
            shutil.copytree(src, dst,
                            copy_function=link_or_copy if cow else shutil.copy2,
                            ignore=shutil.ignore_patterns('*.lock', '*.tmp', '__pycache__'))
        elif src.exists(): shutil.copy2(src, dst)
        else: dst.parent.mkdir(parents=True, exist_ok=True)
        self.writable_paths.append(rel)

    def publish(self, paths=None):
        selected = paths if paths is not None else self.writable_paths
        changes, coverage_section = [], None
        for rel in selected:
            src = self.root / rel
            files = list(src.rglob('*')) if src.is_dir() else [src]
            for p in files:
                if not p.is_file() or p.is_symlink() or p.name.endswith(('.lock', '.tmp')) or p.name.startswith('.'):
                    continue
                relative = p.relative_to(self.root)
                dst = self.origin / relative
                if relative == Path('docs/COVERAGE.md'):
                    start,end='<!-- freezes:start -->','<!-- freezes:end -->'
                    text=p.read_text()
                    if start in text and end in text:
                        coverage_section=start+text.split(start,1)[1].split(end,1)[0]+end
                    continue
                if dst.exists() and digest(p) == digest(dst): continue
                expected = self.baseline.get(str(relative))
                if signature(dst) != expected:
                    raise RuntimeError('Concurrent writer changed ' + str(relative) + '; generation not published')
                changes.append((p, dst))
        # Validate all conflicts before replacing anything. Evidence first.
        changes.sort(key=lambda pair: (not str(pair[1]).startswith(str(self.origin / 'data/raw')), str(pair[1])))
        for src, dst in changes: atomic_publish(src, dst)
        if coverage_section:
            lockpath=self.origin/'data/raw/freezes/.coverage.lock'
            lockpath.parent.mkdir(parents=True,exist_ok=True)
            with lockpath.open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                path=self.origin/'docs/COVERAGE.md'
                text=path.read_text() if path.exists() else '# Coverage\n'
                start,end='<!-- freezes:start -->','<!-- freezes:end -->'
                if start in text and end in text:
                    before,tail=text.split(start,1)
                    _,after=tail.split(end,1)
                    merged=before+coverage_section+after
                else: merged=text.rstrip()+'\n\n'+coverage_section+'\n'
                if merged!=text: atomic(path,merged.encode())
        return len(changes)

    def close(self): self.temp.cleanup()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
