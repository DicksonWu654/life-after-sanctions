"""Fetch public list diffs and dated OFAC actions; never execute upstream code."""
import datetime as dt
import json
import contextlib
import io
import re
import sys
import time
import urllib.error
from sources import fetch, read, index, atomic, RAW

REPO = '0xB10C/ofac-sanctioned-digital-currency-addresses'
EARLY_DATES = '''20181128 20190821 20200302 20200916 20201216 20210406
20210415 20210921 20211108 20220405 20220414 20220422 20220506 20220808
20221108 20250321'''.split()

def collect(refresh=False):
    commits = json.loads(fetch('b10c_commits_1', f'https://api.github.com/repos/{REPO}/commits?sha=lists&per_page=100&page=1', refresh))
    # Pagination is important if the repository grows beyond the present 62 commits.
    page = 2
    batch = commits
    while len(batch) == 100:
        batch = json.loads(fetch(f'b10c_commits_{page}', f'https://api.github.com/repos/{REPO}/commits?sha=lists&per_page=100&page={page}', refresh))
        commits.extend(batch)
        page += 1
    tip = commits[0]['sha']
    tree = json.loads(fetch('b10c_tree', f'https://api.github.com/repos/{REPO}/git/trees/{tip}?recursive=1', refresh))
    for obj in tree['tree']:
        if obj['path'].startswith('sanctioned_addresses_') and obj['path'].endswith('.json'):
            ticker = obj['path'].split('_')[-1].split('.')[0]
            fetch('b10c_current_' + ticker, f'https://raw.githubusercontent.com/{REPO}/{tip}/{obj["path"]}', refresh)
    for commit in reversed(commits):
        sha = commit['sha']
        fetch('b10c_patch_' + sha, f'https://github.com/{REPO}/commit/{sha}.patch')
        time.sleep(0.15)

def collect_actions(refresh=False):
    sitemap = fetch('ofac_sitemap', 'https://ofac.treasury.gov/sitemap.xml', refresh)
    urls = sorted(set(u for u in re.findall(r'<loc>(.*?)</loc>', sitemap.decode())
                      if '/recent-actions/' in u and re.search(r'/20\d{6}', u)
                      and u.rsplit('/',1)[-1] >= '20181128'))
    failures = []
    for i, url in enumerate(urls, 1):
        key = 'action_' + url.rsplit('/',1)[-1]
        if key in index():
            continue
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                fetch(key, url)
        except urllib.error.HTTPError as exc:
            failures.append(dict(url=url, status=exc.code))
            print('action fetch failed', url, exc.code, flush=True)
        if i % 25 == 0:
            print(f'action scan: {i}/{len(urls)} sitemap pages, {len(failures)} failures', flush=True)
        time.sleep(0.25)
    atomic(RAW/'action_scan.json', (json.dumps(dict(urls=urls,failures=failures),indent=2)+'\n').encode())
    print(f'action scan complete: {len(urls)} pages, {len(failures)} failures', flush=True)

if __name__ == '__main__':
    if '--all-actions' in sys.argv:
        collect_actions('--refresh' in sys.argv)
    else:
        collect('--refresh' in sys.argv)
