"""Child entry point: deny network in offline steps and writes outside staging.

This is a guard against accidental I/O, not an adversarial-code sandbox.
"""
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import threading

root = Path(sys.argv[1]).resolve()
offline = sys.argv[2] == 'offline'
script = root / sys.argv[3]
sys.argv = [str(script), *sys.argv[4:]]
sys.path.insert(0, str(script.parent))
sys.path.insert(0, str(root))
sys.dont_write_bytecode = True
copy_lock = threading.RLock()
copy_state = threading.local()

def audit(event, args):
    if getattr(copy_state,'active',False): return
    if offline and event in ('socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.bind'):
        raise RuntimeError('OFFLINE_NETWORK_DENIED: ' + event)
    if event == 'open' and not isinstance(args[0], int):
        flags = args[2] if len(args) > 2 else 0
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            p = Path(args[0]).resolve()
            if not p.is_relative_to(root) and str(p) != '/dev/null':
                raise RuntimeError('WRITE_OUTSIDE_GENERATION: ' + str(p))
            if p.is_file() and p.stat().st_nlink > 1:
                with copy_lock:
                    if p.stat().st_nlink > 1:
                        copy_state.active=True
                        name=None
                        try:
                            fd,name=tempfile.mkstemp(prefix='.'+p.name+'.cow-',dir=p.parent)
                            os.close(fd)
                            shutil.copyfile(p,name)
                            os.replace(name,p)
                        finally:
                            if name: Path(name).unlink(missing_ok=True)
                            copy_state.active=False

sys.addaudithook(audit)
if offline and script.relative_to(root).as_posix() == 'scripts/analysis/flows.py' and '--resume' in sys.argv and '--check' not in sys.argv:
    # Resume rebuilds EDGES from the saved JSON input snapshot, after tracing.
    # Discard only the staging copy so its atomic replacement does not need a
    # third 1.4 GB CSV beside the published and first-pass staged generations.
    edges = root / 'data/derived/flows_edges.csv'
    if not edges.parent.resolve().is_relative_to(root):
        raise RuntimeError('Flow scratch directory escapes staging')
    if edges.exists():
        size = edges.stat().st_size
        edges.unlink()
        print('Released first-pass flow scratch:', size, 'bytes', flush=True)
if offline and script.relative_to(root).as_posix() == 'scripts/freezes/fetch_freezes.py' and '--pipeline-rebuild' in sys.argv:
    namespace = runpy.run_path(str(script), run_name='pipeline_freeze_rebuild')
    report = namespace['outputs'](namespace['load_state']())
    print('Offline freeze rebuild:', report['event_rows'], 'issuer events')
    raise SystemExit(0)
if offline and script.relative_to(root).as_posix() == 'scripts/prices/price.py':
    # Existing --check unconditionally forces a live catalog request. Replay
    # that exact URL from its saved cache, with the socket guard still active.
    namespace = runpy.run_path(str(script), run_name='pipeline_price_check')
    if os.environ.get('LAS_CHECK_AS_OF_UTC'):
        from scripts.lib.price_check_clock import pin
        pin(namespace['main'].__globals__,os.environ['LAS_CHECK_AS_OF_UTC'])
    original = namespace['fetch_json']
    def cached(*args, **kwargs):
        kwargs['force'] = False
        kwargs['retries'] = 1
        return original(*args, **kwargs)
    namespace['main'].__globals__['fetch_json'] = cached
    raise SystemExit(namespace['main']())
runpy.run_path(str(script), run_name='__main__')
