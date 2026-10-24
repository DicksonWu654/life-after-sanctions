"""Fetch only public list data, pinned to the lists branch commit (no upstream code)."""
import csv
import re
from common import Client, ROOT, save

def main():
    c = Client(delay=0.5)
    base = 'https://api.github.com/repos/0xB10C/ofac-sanctioned-digital-currency-addresses'
    commit, commit_ref = c.get(base + '/commits/lists', group='bootstrap')
    sha = commit['sha']
    files, listing_ref = c.get(base + '/contents', {'ref':sha}, group='bootstrap')
    rows = {}
    sources = []
    tickers = []
    excluded = {'ARB','BCH','BSC','BSV','BTG','DASH','ETC','ETH','LTC','XBT','XVG','ZEC'}
    for entry in files:
        m = re.fullmatch(r'sanctioned_addresses_(.+)\.txt', entry['name'])
        if not m:
            continue
        ticker = m[1]
        tickers.append(ticker)
        if ticker in excluded:
            continue
        url = f'https://raw.githubusercontent.com/0xB10C/ofac-sanctioned-digital-currency-addresses/{sha}/{entry["name"]}'
        text, raw = c.get(url, group='bootstrap')
        if not isinstance(text, str):
            raise ValueError('Expected plain text address list')
        count = 0
        for addr in text.splitlines():
            addr = addr.strip()
            if not addr or addr.startswith('#'):
                continue
            chain = ticker.lower()
            if ticker in ('USDT','USDC'):
                if addr.startswith('T'):
                    chain = 'trx'
                elif addr.startswith('0x'):
                    continue
                else:
                    chain = 'unknown'
            rows[(chain,addr)] = {'chain':chain,'address':addr,'source_url':url,'raw_ref':raw}
            count += 1
        sources.append({'ticker':ticker,'count':count,'source_url':url,'raw_ref':raw})
    path = ROOT / 'data/bootstrap/fetch_tron.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w',newline='') as f:
        w = csv.DictWriter(f,fieldnames=['chain','address','source_url','raw_ref'])
        w.writeheader()
        w.writerows(rows[k] for k in sorted(rows))
    save(ROOT / 'data/raw/tron/bootstrap/manifest.json.gz', {'commit':sha,'commit_raw_ref':commit_ref,
         'listing_raw_ref':listing_ref,'tickers_found':tickers,'sources':sources,'address_count':len(rows)})
    from collections import Counter
    print(sha, dict(Counter(row['chain'] for row in rows.values())))

if __name__ == '__main__':
    main()
