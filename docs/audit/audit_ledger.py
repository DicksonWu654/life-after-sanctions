"""Independent, standard-library audit of the OFAC address ledger.

Run from repository root: .venv/bin/python docs/audit/audit_ledger.py
Only writes docs/audit, data/audit, and data/raw/audit.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import random
import re
import tarfile
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw/audit'
OUT = ROOT / 'data/audit'
SEED = 20261024
XML_URL = 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN_ADVANCED.XML'
COMMIT = '6ae2472c439b9bb2788f8df662052ae31854aa97'
TARBALL_URL = f'https://codeload.github.com/0xB10C/ofac-sanctioned-digital-currency-addresses/tar.gz/{COMMIT}'


def raw_fetch(url: str, label: str) -> tuple[bytes, str]:
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / (label + '.gz')
    meta = RAW / (label + '.json')
    if target.exists() and meta.exists():
        return gzip.decompress(target.read_bytes()), str(target.relative_to(ROOT))
    req = Request(url, headers={'User-Agent': 'LedgerAudit/1.0 (research; contact via repository)', 'Accept': '*/*'})
    last = None
    for attempt in range(3):
        try:
            with urlopen(req, timeout=45) as resp:
                body = resp.read()
                status = resp.status
                resolved = resp.url
            break
        except Exception as exc:
            last = exc
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f'fetch failed {url}: {last}')
    with gzip.open(target, 'wb', compresslevel=9) as f:
        f.write(body)
    meta.write_text(json.dumps({'url': url, 'resolved_url': resolved, 'http_status': status,
                                'fetched_at_utc': datetime.now(timezone.utc).isoformat(),
                                'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                                'raw_ref': str(target.relative_to(ROOT))}, indent=2) + '\n')
    return body, str(target.relative_to(ROOT))


def local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def current_xml(body: bytes) -> tuple[list[tuple[str, str, str]], str]:
    """No imports or calls into scripts/ledger. Preserve duplicate XML features."""
    kinds: dict[str, str] = {}
    triples: list[tuple[str, str, str]] = []
    issue = ''
    for _, element in ET.iterparse(io.BytesIO(body), events=('end',)):
        tag = local(element.tag)
        if tag == 'DateOfIssue':
            fields = {local(e.tag): e.text for e in element}
            issue = f'{int(fields["Year"]):04}-{int(fields["Month"]):02}-{int(fields["Day"]):02}'
        elif tag == 'FeatureType' and (element.text or '').startswith('Digital Currency Address - '):
            kinds[element.get('ID', '')] = element.text.partition(' - ')[2].strip()
        elif tag == 'DistinctParty':
            uid = element.get('FixedRef', '')
            for feature in element.iter():
                if local(feature.tag) != 'Feature':
                    continue
                ticker = kinds.get(feature.get('FeatureTypeID', ''))
                if ticker:
                    for detail in feature.iter():
                        if local(detail.tag) == 'VersionDetail' and detail.text:
                            triples.append((ticker, detail.text.strip(), uid))
            element.clear()
    return triples, issue


def canonical_address(address: str) -> str:
    return address.lower() if address.startswith(('0x', 'bc1', 'BC1')) else address


def quote(text: str, address: str) -> str:
    pattern = re.compile(r'Digital\s+Currency\s+Address\s*[-–]\s*([A-Za-z0-9]+)\s+' + re.escape(address), re.I)
    m = pattern.search(text)
    if not m:
        return ''
    return re.sub(r'\s+', ' ', m.group(0)).strip()


class ArticleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ('p', 'h1', 'h2', 'h3', 'h4', 'br', 'li', 'div'):
            self.parts.append('\n')


def page_text(body: bytes) -> str:
    html = body.decode('utf-8', 'replace')
    match = re.search(r'<article\b[^>]*>(.*?)</article>', html, re.I | re.S)
    parser = ArticleText()
    parser.feed(match.group(1) if match else html)
    return ' '.join(''.join(parser.parts).split())


def sample_rows(rows: list[dict]) -> list[tuple[str, dict]]:
    rng = random.Random(SEED)
    selected: list[tuple[str, dict]] = []
    used: set[tuple[str, str]] = set()
    dates: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        dates[row['sdn_uid']].add(row['listed_date'])

    def draw(label: str, number: int, predicate, distinct_uid: bool = False) -> None:
        pool = [r for r in rows if predicate(r) and (r['sdn_uid'], r['address_normalized']) not in used]
        rng.shuffle(pool)
        chosen_uids: set[str] = set()
        for row in pool:
            if distinct_uid and row['sdn_uid'] in chosen_uids:
                continue
            selected.append((label, row))
            used.add((row['sdn_uid'], row['address_normalized']))
            chosen_uids.add(row['sdn_uid'])
            if len(chosen_uids) == number if distinct_uid else sum(x[0] == label for x in selected) == number:
                break
        assert sum(x[0] == label for x in selected) == number, (label, len(pool))

    draw('Tron/USDT', 10, lambda r: r['ticker'] == 'USDT' and r['chain'] == 'TRX')
    draw('BTC', 10, lambda r: r['chain'] == 'BTC')
    draw('ETH', 8, lambda r: r['chain'] == 'ETH' and r['current_in_sdn'] == 'true')
    draw('delisted', 4, lambda r: r['current_in_sdn'] == 'false')
    # UID 39796 was a replacement Tornado Cash record. Its inherited lineage date
    # predates that record, so it does not qualify as a later addition to that UID.
    draw('later addition', 4, lambda r: r['sdn_uid'] != '39796' and r['listed_date'] > min(dates[r['sdn_uid']]), distinct_uid=True)
    draw('general', 4, lambda r: True)
    return selected


def archived_action_index(sample: list[tuple[str, dict]]) -> tuple[dict[str, list[tuple[str, str]]], int]:
    """Independently search the existing complete dated-page archive for discovery.

    The chosen pages are then downloaded afresh; this archive is only the search corpus.
    """
    manifest = json.loads((ROOT / 'data/raw/ofac/manifest.json').read_text())
    needles = {r['address'].lower(): r['address'] for _, r in sample}
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    n_pages = 0
    for name, entry in manifest.items():
        if not name.startswith('action_') or not isinstance(entry, dict) or not entry.get('raw_ref'):
            continue
        url = entry.get('url', '')
        if '/recent-actions/' not in url:
            continue
        raw_path = ROOT / entry['raw_ref']
        if not raw_path.exists():
            continue
        n_pages += 1
        body = gzip.decompress(raw_path.read_bytes())
        hay = page_text(body).lower()
        for needle, original in needles.items():
            if needle in hay:
                stamp = name.partition('action_')[2][:8]
                found[original].append((f'{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}', url))
    return found, n_pages


def format_chain(addr: str) -> str:
    if re.fullmatch(r'0x[0-9a-fA-F]{40}', addr):
        return 'EVM (network unresolved)'
    if re.fullmatch(r'41[0-9a-fA-F]{40}', addr) or re.fullmatch(r'T[1-9A-HJ-NP-Za-km-z]{33}', addr):
        return 'TRX'
    if re.fullmatch(r'(?:bc1[ac-hj-np-z02-9]{11,87}|[13][1-9A-HJ-NP-Za-km-z]{25,34})', addr, re.I):
        return 'BTC'
    return 'other/invalid'


def historical_deletions() -> tuple[list[tuple[str, int, int, str, str]], int]:
    """Scan every saved 0xB10C patch; independently refetch deletion patches."""
    manifest = json.loads((ROOT / 'data/raw/ofac/manifest.json').read_text())
    deletion_patches = []
    count = 0
    for key, entry in manifest.items():
        if not key.startswith('b10c_patch_'):
            continue
        count += 1
        body = gzip.decompress((ROOT / entry['raw_ref']).read_bytes()).decode('utf-8', 'replace')
        day_match = re.search(r'^Date: (.*)$', body, re.M)
        if not day_match:
            continue
        day = parsedate_to_datetime(day_match.group(1)).date().isoformat()
        section = False
        deleted = []
        added = []
        for line in body.splitlines():
            if line.startswith('diff --git '):
                section = bool(re.search(r'sanctioned_addresses_[A-Z0-9]+\.txt', line))
                continue
            if not section or line.startswith(('--- ', '+++ ')):
                continue
            if line.startswith('-'):
                deleted.append(line[1:].strip())
            elif line.startswith('+'):
                added.append(line[1:].strip())
        if deleted:
            added_lower = {x.lower() for x in added}
            case_only = sum(x.lower() in added_lower for x in deleted)
            fresh_body, fresh_ref = raw_fetch(entry['url'], f'b10c_deletion_patch_{day}')
            assert fresh_body.decode('utf-8', 'replace') == body, f'patch changed: {entry["url"]}'
            deletion_patches.append((day, len(deleted), case_only, entry['url'], fresh_ref))
    return sorted(deletion_patches), count


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader((ROOT / 'data/ledger.csv').open(newline='')))
    sample = sample_rows(rows)
    found, scanned_pages = archived_action_index(sample)
    xml, xml_ref = raw_fetch(XML_URL, 'sdn_advanced_20261023')
    xml_features, issue = current_xml(xml)
    xml_set = {(t, canonical_address(a), u) for t, a, u in xml_features}
    ledger_features = set()
    for row in rows:
        if row['current_in_sdn'] != 'true':
            continue
        for f in json.loads(row['feature_records']):
            ledger_features.add((f['ticker'], canonical_address(f['address']), row['sdn_uid']))
    missing_ledger = sorted(xml_set - ledger_features)
    missing_xml = sorted(ledger_features - xml_set)

    audit = []
    prior_evidence = []
    for slot, (stratum, row) in enumerate(sample, 1):
        appearances = sorted(set(found.get(row['address'], [])))
        if appearances:
            date = appearances[0][0]
            url = appearances[0][1]
        else:
            date, url = '', ''
        excerpt = ''
        raw_ref = ''
        reason = ''
        if url:
            body, raw_ref = raw_fetch(url, f'action_{date.replace("-", "")}_{hashlib.sha256(url.encode()).hexdigest()[:10]}')
            excerpt = quote(page_text(body), row['address'])
            if not excerpt:
                reason = 'fresh OFAC page lacks exact Digital Currency Address text'
        else:
            reason = 'address absent from archived OFAC Recent Actions search corpus'
        if not excerpt:
            verdict = 'CANNOT_VERIFY'
        elif date != row['listed_date']:
            verdict = 'DATE_MISMATCH'
            reason = 'earliest dated action mentioning address differs from ledger date'
        elif url != row['listed_action_url']:
            verdict = 'URL_MISMATCH'
            reason = 'earliest dated action URL differs from ledger URL'
        else:
            verdict = 'MATCH'
            reason = 'exact address text on freshly fetched earliest indexed action page'
        prior_date = prior_url = prior_ref = prior_excerpt = ''
        prior_absent = ''
        if stratum == 'later addition':
            earlier = min((r for r in rows if r['sdn_uid'] == row['sdn_uid'] and r['listed_date'] < row['listed_date']),
                          key=lambda r: r['listed_date'])
            prior_date, prior_url = earlier['listed_date'], earlier['listed_action_url']
            prior_body, prior_ref = raw_fetch(prior_url, f'action_{prior_date.replace("-", "")}_{hashlib.sha256(prior_url.encode()).hexdigest()[:10]}')
            prior_text = page_text(prior_body)
            prior_excerpt = quote(prior_text, earlier['address'])
            prior_absent = str(row['address'].lower() not in prior_text.lower()).lower()
            if not prior_excerpt or prior_absent != 'true':
                verdict = 'CANNOT_VERIFY'
                reason = 'earlier same-UID page does not establish a clean later address addition'
            prior_evidence.append((row['sdn_uid'], prior_date, prior_url, prior_excerpt,
                                   prior_absent, row['listed_date'], prior_ref))
        audit.append({'sample_no': slot, 'stratum': stratum, 'address': row['address'],
                      'sdn_uid': row['sdn_uid'], 'sdn_name': row['sdn_name'], 'ticker': row['ticker'],
                      'chain': row['chain'], 'ledger_date': row['listed_date'],
                      'ledger_url': row['listed_action_url'], 'audit_date': date, 'audit_url': url,
                      'exact_excerpt': excerpt, 'verdict': verdict, 'reason': reason,
                      'raw_ref': raw_ref, 'source_url': url, 'all_indexed_appearance_count': len(appearances),
                      'entity_prior_date': prior_date, 'entity_prior_url': prior_url,
                      'entity_prior_excerpt': prior_excerpt, 'sampled_address_absent_on_prior_page': prior_absent,
                      'entity_prior_raw_ref': prior_ref})
    with (OUT / 'ledger_audit.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)

    # Third-party baseline pinned to the same commit claimed by docs/LEDGER.md.
    tar_bytes, tar_ref = raw_fetch(TARBALL_URL, 'b10c_6ae2472c_tarball')
    b10c = set()
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode='r:gz') as archive:
        for member in archive:
            m = re.search(r'/sanctioned_addresses_([A-Z0-9]+)\.txt$', member.name)
            if not m:
                continue
            ticker = m.group(1)
            content = archive.extractfile(member).read().decode('utf-8')
            for line in content.splitlines():
                address = line.strip()
                if address and not address.startswith('#'):
                    b10c.add((ticker, canonical_address(address)))
    ofac_pairs = {(t, a) for t, a, _ in xml_set}
    ofac_not_b10c = sorted(ofac_pairs - b10c)
    b10c_not_ofac = sorted(b10c - ofac_pairs)
    ofac_by_address: dict[str, set[str]] = defaultdict(set)
    b10c_by_address: dict[str, set[str]] = defaultdict(set)
    for ticker, address in ofac_pairs:
        ofac_by_address[address].add(ticker)
    for ticker, address in b10c:
        b10c_by_address[address].add(ticker)
    shared_ticker_disagreements = [(a, sorted(ofac_by_address[a]), sorted(b10c_by_address[a]))
                                   for a in sorted(ofac_by_address.keys() & b10c_by_address.keys())
                                   if ofac_by_address[a] != b10c_by_address[a]]
    deletion_patches, patch_count = historical_deletions()

    mapping = []
    for row in rows:
        if not set(row['tickers'].split(';')) & {'USDT', 'USDC', 'ETH'}:
            continue
        inferred = format_chain(row['address'])
        actual = row['chain']
        disagreement = ((inferred == 'TRX' and actual != 'TRX') or
                        (inferred == 'BTC' and actual != 'BTC') or
                        (inferred == 'EVM (network unresolved)' and actual not in ('ETH', 'ARB', 'BSC', 'ETC')) or
                        (inferred == 'other/invalid' and row['address_valid'] == 'true'))
        mapping.append((row, inferred, disagreement))
    mapping_disagreements = [(r, inferred) for r, inferred, bad in mapping if bad]
    mapping_invalid = [(r, inferred) for r, inferred, _ in mapping if inferred == 'other/invalid']
    format_counts = Counter(inferred for _, inferred, _ in mapping)

    def md(s) -> str:
        return str(s).replace('|', '\\|').replace('\n', ' ')

    vcount = Counter(a['verdict'] for a in audit)
    lines = ['# Independent OFAC ledger audit', '',
             f'Run seed: `{SEED}`. Sample: **{len(audit)} address–entity rows**. Search corpus: **{scanned_pages} saved OFAC Recent Actions pages**; the selected source pages were freshly fetched and archived below. Search is limited to those indexed pages, so “first” means earliest in this corpus. Source copies are under `data/raw/audit/`.', '',
             '## 40-row source-text sample', '',
             '| # | Stratum | UID / entity | Ticker / chain | Address | Ledger date | Audit first date | Audit source URL | Exact OFAC excerpt naming address | Verdict | Reason | Raw ref |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for a in audit:
        lines.append('| ' + ' | '.join(md(v) for v in (a['sample_no'], a['stratum'], a['sdn_uid'] + ' / ' + a['sdn_name'],
                       a['ticker'] + ' / ' + a['chain'], a['address'], a['ledger_date'], a['audit_date'],
                       a['audit_url'], a['exact_excerpt'], a['verdict'], a['reason'], a['raw_ref'])) + ' |')
    lines += ['', 'Verdicts: ' + ', '.join(f'**{vcount.get(k, 0)} {k}**' for k in ('MATCH','DATE_MISMATCH','URL_MISMATCH','CANNOT_VERIFY')) + '. Entity names, full URLs, and exact excerpts are also in `data/audit/ledger_audit.csv`.', '',
              '### Later additions to existing entries', '',
              '| UID | Earlier action date / URL | Earlier address excerpt | Sampled address absent on earlier page? | New address date | Earlier page raw ref |',
              '| --- | --- | --- | --- | --- | --- |']
    for uid, day, url, excerpt, absent, new_day, ref in prior_evidence:
        lines.append('| ' + ' | '.join(md(x) for x in (uid, f'{day} / {url}', excerpt, absent, new_day, ref)) + ' |')
    lines += ['',
              '## Current SDN advanced XML set comparison', '',
              f'- Fresh official export: [SDN_ADVANCED.XML]({XML_URL}); issue date **{issue}**; SHA-256 `{hashlib.sha256(xml).hexdigest()}`; raw ref `{xml_ref}`.',
              f'- XML feature records: **{len(xml_features)}**; unique `(ticker, canonical address, SDN UID)` triples: **{len(xml_set)}**.',
              f'- Current ledger rows: **{sum(r["current_in_sdn"] == "true" for r in rows)}**; unique feature triples from `feature_records`: **{len(ledger_features)}**.',
              f'- XML-only triples: **{len(missing_ledger)}**; ledger-only triples: **{len(missing_xml)}**.', '']
    for label, items in [('XML-only', missing_ledger), ('ledger-only', missing_xml)]:
        for triple in items:
            lines.append(f'- {label}: `{triple}`')
    lines += ['', 'The comparison uses the complete `feature_records` array for each current ledger row, because a row can hold several ticker features; `ticker` is only representative. EVM and bech32 case is normalized, preserving the literal source label.', '',
              '## Address-format chain check', '',
              f'- Checked **{len(mapping)} address–entity rows** containing USDT, USDC, or ETH in `tickers`; valid-format chain disagreements: **{len(mapping_disagreements)}**; invalid-format source strings: **{len(mapping_invalid)}**.',
              '- Format counts across those rows: ' + ', '.join(f'**{format_counts.get(k, 0)} {k}**' for k in ('EVM (network unresolved)', 'TRX', 'BTC', 'other/invalid')) + '.',
              '- `0x` plus 40 hex characters establishes an EVM address, but not which EVM network. ETH chain assignments for stablecoin EVM addresses are therefore convention-based and cannot be independently proved by address format.', '']
    for r, inferred in mapping_disagreements:
        lines.append(f'- UID `{r["sdn_uid"]}`, `{r["address"]}`: ledger chain `{r["chain"]}`; format `{inferred}`; source `{r["source_url"]}`.')
    for r, inferred in mapping_invalid:
        lines.append(f'- Invalid-format source string, UID `{r["sdn_uid"]}`, `{r["address"]}`: ticker `{r["ticker"]}`, ledger chain `{r["chain"]}`, format `{inferred}`, `address_valid={r["address_valid"]}`. This is already flagged as invalid in the ledger; the source value does not establish a usable chain address. Evidence: `{r["listed_action_url"]}`.')
    lines += ['', '## 0xB10C pinned-current comparison', '',
              f'- Pin: `{COMMIT}`; source `{TARBALL_URL}`; raw ref `{tar_ref}`; SHA-256 `{hashlib.sha256(tar_bytes).hexdigest()}`.',
              f'- OFAC-only ticker/address pairs: **{len(ofac_not_b10c)}**; 0xB10C-only pairs: **{len(b10c_not_ofac)}**; shared-address ticker-set disagreements: **{len(shared_ticker_disagreements)}**.', '']
    for t, a in ofac_not_b10c:
        lines.append(f'- OFAC-only: `{t}` `{a}`')
    for t, a in b10c_not_ofac:
        lines.append(f'- 0xB10C-only: `{t}` `{a}`')
    for address, ofac_tickers, b10c_tickers in shared_ticker_disagreements:
        lines.append(f'- Shared address `{address}`: OFAC `{ofac_tickers}`; 0xB10C `{b10c_tickers}`.')
    lines += ['', f'Historical `.txt` deletion check: **{patch_count} saved dated patches** scanned with this script; deletion patches were fetched again into `data/raw/audit/`.', '',
              '| Commit day (UTC) | Raw address deletions | Case-only changes | Fresh patch URL | Raw ref |',
              '| --- | ---: | ---: | --- | --- |']
    for day, deletions, case_only, url, ref in deletion_patches:
        lines.append(f'| {day} | {deletions} | {case_only} | {url} | `{ref}` |')
    lines += ['', '## Concrete fixes', '']
    fixes = []
    for a in audit:
        if a['verdict'] == 'DATE_MISMATCH':
            fixes.append(f'- Ledger row UID `{a["sdn_uid"]}` / `{a["address"]}`: set `listed_date` to `{a["audit_date"]}`; evidence `{a["audit_url"]}` (`{a["raw_ref"]}`).')
        elif a['verdict'] == 'URL_MISMATCH':
            fixes.append(f'- Ledger row UID `{a["sdn_uid"]}` / `{a["address"]}`: set `listed_action_url` to `{a["audit_url"]}`; evidence `{a["raw_ref"]}`.')
    if mapping_disagreements:
        for r, inferred in mapping_disagreements:
            fixes.append(f'- Ledger row UID `{r["sdn_uid"]}` / `{r["address"]}`: review `chain={r["chain"]}` against `{inferred}`; evidence `{r["source_url"]}`.')
    if missing_ledger or missing_xml:
        fixes.append('- Reconcile the explicit XML/ledger triple differences above using the fresh official export.')
    lines += fixes or ['- No confirmed ledger field fixes from these checks.']
    lines += ['', '## Method and limits', '',
              '- Sampling uses Python `random.Random` with the recorded seed, sequential draws without replacement, and distinct SDN UIDs for the four later-addition slots. A later addition is a row whose `listed_date` exceeds the earliest listed date for that same UID in the ledger. Replacement Tornado Cash UID 39796 is excluded from this stratum because its earlier dates belong to the predecessor UID lineage.',
              '- The audit searches every `action_*` page in the preexisting OFAC archive using this script’s own HTML extraction, selects the earliest date containing the literal address, then independently re-downloads that page and records the exact digital-currency phrase (HTML whitespace normalized). A repeated mention on an earlier page for a different entity could require entry-level review; the table retains all relevant IDs and URLs for that review.',
              '- Date and URL verdicts concern first address appearance in the searched action corpus. They do not infer legal status from an address feature removal. Current XML is a separate live download; a source update between ledger build and audit can create a valid time-of-snapshot difference.',
              '- Ticker/chain checks are format checks, not network activity checks. `0x` addresses have unresolved EVM network by shape alone.', '']
    (ROOT / 'docs/audit/LEDGER_AUDIT.md').write_text('\n'.join(lines))
    print(json.dumps({'sample': len(audit), 'verdicts': vcount, 'xml_features': len(xml_features),
                      'xml_only': len(missing_ledger), 'ledger_only': len(missing_xml),
                      'mapping_disagreements': len(mapping_disagreements),
                      'invalid_format': len(mapping_invalid), 'historical_patches': patch_count,
                      'ofac_not_b10c': len(ofac_not_b10c), 'b10c_not_ofac': len(b10c_not_ofac),
                      'scanned_pages': scanned_pages}, indent=2))


if __name__ == '__main__':
    main()
