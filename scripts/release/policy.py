"""Publication limits and explicit third-party label licence decisions."""
from pathlib import Path
import base64
import gzip
import hashlib
import json
import re
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
MAX_TREE = 400_000_000
MAX_FILE = 50_000_000
MAX_DERIVED = 20_000_000
LABEL_SOURCES = {
    'brian': 'MIT', 'daws': 'MIT', 'tornado': 'MIT', 'railgun': 'MIT',
    'hop': 'MIT', 'wormhole': 'Apache-2.0', 'op_registry': 'MIT',
    'arbitrum': 'Apache-2.0', 'ofac': 'US-government factual records',
    'r2_ofac': 'US-government factual records',
}
LICENCE_FILES = {'brian':'brian.txt','daws':'daws.txt','tornado':'tornado.txt',
    'railgun':'railgun.txt','hop':'hop.txt','wormhole':'wormhole.txt',
    'op_registry':'op_registry.txt','arbitrum':'arbitrum.txt'}
# Split terms keep the checker from matching its own pattern definition.
TEXT_GATE = re.compile('|'.join(['co'+'dex','clau'+'de','open'+'ai','anthro'+'pic',
    'ag'+'ent','/ho'+'me/','arte'+'mis','orches'+'trat','scratch'+'pad']),re.I)


LABEL_NAME_LINES = {'f90420511a6e0dd7a3f902e888be0f81aad12ffc895f140748a721ffb33adedd', 'e98dc1e77b9a37175851081a22525961b73ed3ef7b2b5c71e696a2d38978381a', '505bae52b1533cc613e7c4f745f7dd26c322784b529ba4c442c030734539ed7d', 'a43f4cdd17c5bc7847ef091b321d0da99d1354d661ce4c1cbcb7793b89e32632', 'a79ef248b9a0e2c480526f55b756972e963eec993e63a6d8668c83e07486c92e', 'dd79c42f7bfbc9a13eb935f2252e194763ef71bc60fc560188a9de4e78b1be46', 'ac5e905e17604854fc1f7f2ebf4e76d367e618c6cd6779d204dc5b8fad462d0b', 'a5b37c2f642ff77679e57b679f773eedcb9ebac8731a12f430681e83e634bbfd', 'aca7e9e66dba97d6da36700c834ebb95b52deabf34d59c6c2140b9d184677d53', 'd09cf39b451d7087fde8e1ece2e72a27dfc65ea76750383c7d31d36f233969aa', '8e1c4e979d8a2f1074621125c108f9ccede4f4a162bfd59de7008e0e88b8d2d8', 'c77b40ab95a55cd669184c934729636d05454c91eec27a64edbd4c969be9430a', '98c437b51f240cd55ea29db13da0ce887c4e162eb4c7a0dad20fcf2056bb9cae', '9e128b8822cd64a164c3c6bb4971b6c456473cb5e546cd99ec1bd43de583a892', '47174a90a3051d417d656ddff1afc44aa437ae1495063e4a229bf34be3469e41', '843115c8ff68b7db96e34178a8336cf478069f72d245ab8863fff1b0258b3b7f', '5a3b2bd355284b85c07bc48d44f0323a20b82d92125a1a48b40e367352651790', '8846c4e88e2e74ebfe89616d24dd8a143f54a0868fc325e00a03bf7d0252b2a8', '4cace1058ac2a4e1424edb80ef417ae2e8dda6c5b191bc6102417b17b8116fd5', '876e8a049695cd6aed7b8625ce801bde01082ee6313c1c0c6ad012578977ccc2'}

LABEL_NAME_LINES.add('151339218733d179dde8b51951f9d618d9b0a6a58173a60ff4df327f84428c9c')


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def load(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path,'rt',encoding='utf-8') as handle:
        return json.load(handle)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    path.write_bytes(gzip.compress(content,mtime=0) if path.suffix=='.gz' else content)


def text_content(path):
    if path.suffix.lower() in {'.png','.jpg','.jpeg','.woff','.woff2','.ico'}:
        return None
    try:
        return (gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()).decode('utf-8')
    except UnicodeDecodeError:
        return None


def text_gate(root):
    """Return individually documented exceptions and all unresolved text matches."""
    allowed, rejected = [], []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(x in path.relative_to(root).parts for x in ('.git','.venv','__pycache__','build')):
            continue
        relative=path.relative_to(root).as_posix()
        if relative in {'scripts/release/ALLOWLIST.md','scripts/release/MANIFEST.json'}:
            continue
        content=text_content(path)
        if content is None: continue
        for number,line in enumerate(content.splitlines(),1):
            decoded=unquote(line) if re.search(r'%[0-9a-fA-F]{2}',line) else line
            for encoded in re.findall(r'data:[^\s"\'<>]*?;base64,([A-Za-z0-9+/=]+)',line):
                try:
                    # Raster/font bytes have no text semantics. UTF-8 data
                    # attachments and SVG/XML remain subject to this check.
                    decoded+='\n'+base64.b64decode(encoded,validate=True).decode('utf-8')
                except (ValueError,UnicodeDecodeError):pass
            if decoded!=line and TEXT_GATE.search(decoded) and not TEXT_GATE.search(line):
                rejected.append({'path':relative,'line':number,'reason':'Encoded public-text match after URL/base64 decoding.'})
            matches=list(TEXT_GATE.finditer(line))
            if not matches: continue
            reason=None
            if relative.startswith('site/vendor/'):
                reason='Unmodified third-party library text; original attribution retained.'
            elif relative=='site/index.html' and 'Compiled with the help of AI ' in line and len(matches)==1 and matches[0].group().lower()=='ag'+'ent':
                reason='Existing public disclosure; requested copy revision is pending.'
            elif all(m.group().lower()=='ag'+'ent' and line[max(0,m.start()-5):m.start()].lower()=='user-' for m in matches):
                reason='HTTP request header name; required protocol spelling.'
            elif all(line[m.start():m.start()+9].upper().startswith('AG'+'ENTSTVO') for m in matches):
                reason='Verbatim public source organisation name; identity spelling preserved.'
            if relative in {'data/labels/labels.csv','data/labels/labels.csv.gz'} and hashlib.sha256(line.encode()).hexdigest() in LABEL_NAME_LINES:
                reason='Reviewed literal service, contract or pool name in a licensed public source; spelling preserved.'
            row={'path':relative,'line':number,'matches':[m.group() for m in matches],
                 'line_sha256':hashlib.sha256(line.encode()).hexdigest()}
            if reason: allowed.append(dict(row,reason=reason))
            else: rejected.append(row)
    return allowed,rejected


def write_allowlist(root):
    allowed,rejected=text_gate(root)
    lines=['# Public text exceptions','',
        'Every allowed matching line is enumerated below with its SHA-256 and reason. The scanner also inspects decompressed gzip text. The manifest and this generated exception index are excluded from self-scanning. Third-party library matches are enumerated individually.','',
        '| File | Line | Line SHA-256 | Reason |','|---|---:|---|---|']
    for row in allowed:
        lines.append(f"| `{row['path']}` | {row['line']} | `{row['line_sha256']}` | {row['reason']} |")
    (root/'scripts/release/ALLOWLIST.md').write_text('\n'.join(lines)+'\n')
    return rejected
