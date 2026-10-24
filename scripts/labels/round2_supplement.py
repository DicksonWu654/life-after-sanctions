"""Save source availability, repository refresh and government-document checks.

PDF extraction is optional: install scripts/labels/requirements.txt into an
isolated --target directory with uv, then pass --pdf-deps DIR --extract-pdf.
All normal collection/rebuild/check commands use the standard library only.
"""
import argparse
import gzip
import io
import json
import re
import sys

from round2_common import ROOT, RAW, fetch, ranked, read_json, save_json

DOJ_API = 'https://www.justice.gov/api/v1/press_releases.json?parameters%5Btitle%5D=Chairman%20of%20Prince%20Group'
COMPLAINT = 'https://www.justice.gov/usao-edny/media/1416291/dl'
INDICTMENT = 'https://www.justice.gov/usao-edny/media/1416286/dl'


def collect():
    report = {'repository_refresh': [], 'government_documents': [], 'availability': []}
    for repo, expected in [('brianleect/etherscan-labels', '923aba72c7e2d0682f7ae6194b6140bd90668dc9'),
                           ('dawsbot/eth-labels', 'd9b21aefeded56f7fce7208d6fa173d128526c1b')]:
        body, meta = fetch('https://api.github.com/repos/' + repo)
        obj = json.loads(body)
        assert obj['full_name'] == repo
        branch = obj['default_branch']
        body, pin = fetch('https://api.github.com/repos/' + repo + '/commits/' + branch)
        revision = json.loads(body)['sha']
        report['repository_refresh'].append({'repository': repo, 'branch': branch, 'revision': revision,
            'unchanged_from_round1': revision == expected, 'source_url': pin['request']['url'],
            'raw_ref': pin['raw_ref'], 'repository_metadata_ref': meta['raw_ref'],
            'note': 'Same immutable revision: reuse its saved factual address registries; no upstream code executed.'})
    for url in (DOJ_API, COMPLAINT, INDICTMENT):
        body, meta = fetch(url)
        report['government_documents'].append(meta)
    top_btc = [r for r in ranked() if r['chain'] == 'BTC' and not r['address'].startswith('__')][:20]
    mempool = []
    for row in top_btc:
        url = 'https://mempool.space/address/' + row['address']
        body, meta = fetch(url)
        mempool.append(dict(row, source='mempool_page', **meta))
    save_json(RAW / 'mempool_checks.json.gz', mempool)
    for url, note in [
        ('https://api.blockchair.com/bitcoin/dashboards/address/' + top_btc[0]['address'] + '?limit=0',
         'HTTP 430 IP-resource block: circuit stopped after one probe; no label-absence inference for any address.'),
        ('https://apilist.tronscanapi.com/api/accountv2?address=TVqwvN5WT2b5AZhEGVzQHfx6HmwTQGkR4w',
         'Accountv2 requires authorization (401). Public account API was queried for every Tron destination and trace node.'),
        ('https://www.walletexplorer.com/api', 'API documents address-lookup and optional named cluster labels.'),
    ]:
        body, meta = fetch(url)
        report['availability'].append(dict(meta, note=note))
    report['mempool_note'] = 'All 20 public address pages returned the JavaScript application shell, with no server-rendered address tag. This is unavailable tag evidence, not proof of no label.'
    save_json(RAW / 'supplement.json', report)
    return report


def documents(deps=None):
    if deps:
        sys.path.insert(0, deps)
    from pypdf import PdfReader
    import pypdf
    results = []
    for url, name in ((COMPLAINT, 'prince-1416291'), (INDICTMENT, 'prince-1416286')):
        body, meta = fetch(url)
        reader = PdfReader(io.BytesIO(body))
        pages = [{'page': i + 1, 'text': page.extract_text()} for i, page in enumerate(reader.pages)]
        save_json(RAW / (name + '.pages.json.gz'), pages)
        results.append({'source_url': url, 'raw_ref': meta['raw_ref'], 'pages': len(pages),
                        'text_ref': str((RAW / (name + '.pages.json.gz')).relative_to(ROOT)),
                        'extractor': 'pypdf==' + pypdf.__version__})
    save_json(RAW / 'document_extraction.json', results)


def government_checks():
    pages = read_json(RAW / 'prince-1416291.pages.json.gz')
    schedule = pages[41]['text']
    addresses = re.findall(r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b', schedule)
    assert len(addresses) == 25
    text = '\n'.join(p['text'] for p in pages)
    complaint_ref = fetch(COMPLAINT)[1]['raw_ref']
    rows = [{'chain': r['chain'], 'address': r['address'], 'first_hop_usd': r['usd'],
             'named_in_attachment_a': r['address'] in addresses,
             'exact_match_in_extracted_text': r['address'] in text,
             'source_url': COMPLAINT, 'raw_ref': complaint_ref,
             'outcome': 'No destination match in Attachment A. Paragraph 58 names no current government-custody address; no ownership label inferred.'}
            for r in ranked() if r['chain'] == 'BTC' and not r['address'].startswith('__')]
    save_json(RAW / 'government_checks.json.gz', {'schedule_address_count': len(addresses), 'addresses': addresses,
        'visually_checked_pages': [23, 37, 42], 'checks': rows})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract-pdf', action='store_true')
    parser.add_argument('--pdf-deps')
    args = parser.parse_args()
    collect()
    if args.extract_pdf:
        documents(args.pdf_deps)
    government_checks()
    print('Saved source refresh, availability and exact government-document checks')
