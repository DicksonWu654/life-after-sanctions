"""Deterministic acceptance report generated from the same evidence as the CSVs."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from chains import assign, EXPLORERS
from sources import ROOT, RAW, read_entry

def esc(value):
    return str(value).replace('|','\\|').replace('\n',' ')

def table(headers, rows):
    lines = ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']
    lines.extend('| '+' | '.join(esc(v) for v in row)+' |' for row in rows)
    return '\n'.join(lines)+'\n'

def render(ledger, addresses, actions, report, pages, manifest):
    active = [r for r in ledger if r['current_in_sdn']=='true']
    historical = [r for r in ledger if r['current_in_sdn']=='false']
    unknown = [r for r in ledger if r['listed_date_method']=='unknown']
    malformed = [r for r in ledger if r['address_valid']=='false']
    tornado_old = [r for r in ledger if r['sdn_uid']=='38499']
    tornado_new = [r for r in ledger if r['sdn_uid']=='39796']
    tornado_overlap = len({r['address_normalized'] for r in tornado_old} & {r['address_normalized'] for r in tornado_new})
    reviews_path = ROOT/'scripts/ledger/manual_verification.json'
    sample = json.loads(reviews_path.read_text()) if reviews_path.exists() else {'reviews':[]}
    valid_reviews = []
    for review in sample['reviews']:
        matches = [r for r in ledger if r['sdn_uid']==review['sdn_uid'] and r['address'].lower()==review['address'].lower()]
        meta = next((v for v in manifest.values() if v['raw_ref']==review['raw_ref']),None)
        page = next((p for p in pages if p['url']==review['url']),None)
        if matches and meta and page and review.get('reviewed') and any(
                review['address'].lower() in m['text'].lower() and review['quote'] in m['text'] for m in page['mentions']):
            valid_reviews.append(review)
    lines = ['# OFAC digital-currency ledger', '',
        f'Generated offline by `scripts/ledger/build_ledger.py`. Current OFAC XML issue date: **{report["issue"]}**. '
        'Research evidence, not legal or compliance advice.', '',
        '## Rebuild and acceptance', '',
        'Run from the repository root. Python standard library only; no additional dependencies:', '',
        '```sh\n.venv/bin/python scripts/ledger/build_ledger.py\n.venv/bin/python scripts/ledger/build_ledger.py --check\n.venv/bin/python scripts/ledger/build_ledger.py --fetch\n```', '',
        '`--check` performs no network requests or writes and compares all three CSVs and this report byte-for-byte. '
        '`--fetch` refreshes the official exports, pinned GitHub lists, sitemap, and newly discovered action pages; '
        'existing dated pages and immutable historical snapshots are reused. Repeated offline builds are byte-identical. '
        'Changed files use fsync plus atomic rename. No commits or pushes are made.', '',
        table(['Check','Result / unit'],[
            ('Current XML digital-currency features',f'{report["feature_count"]}; all preserved, including duplicate features'),
            ('Distinct current source address strings (canonical case)',report['distinct_source_addresses']),
            ('Distinct address strings among current ledger rows',len({r['address_normalized'] for r in active})),
            ('Current address–entity UID pairs / ledger rows',f'{report["current_pairs"]} / {len(active)}'),
            ('Current entity UID records',report['current_entities']),
            ('Current chain–address pairs',sum(r['current_in_sdn']=='true' for r in addresses)),
            ('All address–entity UID rows',len(ledger)),
            ('All distinct chain–address pairs',len(addresses)),
            ('All distinct entity UID records',len({r['sdn_uid'] for r in ledger})),
            ('OFAC action dates touching addresses',len(actions)),
            ('Rows with listing date + dated action URL',f'{len(ledger)-len(unknown)}/{len(ledger)} ({100*(len(ledger)-len(unknown))/len(ledger):.2f}%)'),
            ('Unknown listing dates',f'{len(unknown)} ({100*len(unknown)/len(ledger):.2f}%; target <2%)'),
            ('Missing recovered SDN UIDs',report['unknown_uid_rows']),
            ('Source-text-reviewed random rows',f'{len(valid_reviews)} / 20'),
            ('Historical removed address–entity pairs',len(historical)),
            ('Trackable / untrackable address–entity rows',f'{sum(r["trackable"]=="true" for r in ledger)} / {sum(r["trackable"]=="false" for r in ledger)}'),
            ('Malformed literal source strings',len(malformed)),
            ('Consolidated non-SDN digital-currency features',report['consolidated_count']),
            ('Current OFAC tickers in mapping table',len(report['by_ticker'])),
            ('SDN.XML vs advanced XML',f'exact UID/ticker/address multiset equality: {report["feature_count"]} features in each'),
        ]), '',
        'The source contains more entity links than distinct addresses, and more features than entity links. '
        'A literal requirement that the number of ledger *rows* equal distinct source addresses conflicts with '
        'the one-row-per-(address, SDN UID) contract. The equal distinct-address counts above are the completeness check; '
        'the additional entity links and ticker features are retained, not dropped to force equality.', '',
        '## Source archive', '',
        'All response bodies are gzip-compressed, content-addressed objects under `data/raw/ofac/objects/`. '
        '`data/raw/ofac/manifest.json` maps each logical request to its URL, resolved URL, fetch timestamp, '
        'HTTP status, byte count, SHA-256 of the **uncompressed response**, and `raw_ref`. '
        '`fetches.jsonl` retains previous fetch metadata; changed bytes remain available after refresh. '
        'CSV rows link to their XML/page objects; `listed_raw_ref` and `delisted_raw_ref` identify dated-page evidence.', '',
        table(['Source','Fetched UTC','SHA-256','Raw reference'],[
            (f'[{key}]({manifest[key]["url"]})',manifest[key]['fetched_at'],manifest[key]['sha256'],manifest[key]['raw_ref'])
            for key in ['sdn_advanced','sdn','consolidated_advanced']]), '',
        f'The saved sitemap scan enumerates **{len(json.loads((RAW/"action_scan.json").read_text())["urls"])}** action pages '
        f'since 2018-11-28, with **{len(json.loads((RAW/"action_scan.json").read_text())["failures"])}** fetch failures. '
        f'**{report["actions_scanned"]}** dated pages are parsed (the cache also includes investigated seed URLs). '
        'The archive covers suffixed URLs such as `20240528_33`; guessing unsuffixed URLs alone misses real address additions. '
        'This establishes completeness within OFAC’s current sitemap, not a guarantee about unpublished or removed historical pages.', '',
        'Archived OFAC SDN.XML bytes via the Internet Archive recover historical UID/name/program associations:', '',
        table(['Snapshot request','Raw reference'],[(f'[{k}]({v["url"]})',v['raw_ref']) for k,v in sorted(manifest.items()) if k.startswith('historic_sdn_')]), '',
        '## Schema and date rules', '',
        '`data/ledger.csv` has one row per canonical address and SDN entity UID, preserving source casing in `address`. '
        '`ticker` and `chain` are representative values for compatibility; **use `tickers`, `chains`, and JSON `feature_records` '
        'for complete coverage**. In particular, one address is explicitly listed for ETH/ARB/BSC and one for ETH/ETC. '
        '`data/addresses.csv` expands these into separate chain–address rows. A shared address is also allowed under multiple entities. '
        'All advanced feature IDs remain in `source` and `feature_records`; the duplicated BLENDER.IO XBT feature is retained in the feature count.', '',
        'Listing dates come from explicit addition sections or address differences between OFAC’s “-to-” before/after records. '
        'Unchanged addresses in a later update do not acquire that update date. Alias repetitions collapse to the XML UID. '
        '`listed_date` is first address publication for that entity lineage; `entity_record_listed_date` records when a replacement UID first lists it. '
        '`listing_events` retains each address addition/removal on the row. Each established date has method `recent_actions_page`, '
        'confidence `high`, a URL, and its saved page. A missing exact date would remain blank with method `unknown` and a reason.', '',
        '`actions.csv` has one row per calendar action date. Multiple pages on that date have semicolon-separated URLs and titles. '
        '`n_addresses_added`/`n_addresses_removed` count distinct canonical address strings in explicit additions/deletions and before/after changes, '
        'not ticker features, aliases, entities, or first-ever-only publications. A same-day withdrawal/redesignation can appear in both columns; '
        '`n_addresses_added_and_removed` makes this overlap explicit. Administrative updates can have zero additions and zero removals.', '',
        '## Current counts by OFAC ticker', '',
        table(['Ticker','XML features','Distinct addresses carrying ticker'],[
            (t,report['by_ticker'][t],len({f['address'].lower() if f['address'].startswith('0x') else f['address'] for r in active for f in json.loads(r['feature_records']) if f['ticker']==t}))
            for t in sorted(report['by_ticker'])]), '',
        'Ticker counts overlap when the same address is listed for multiple assets. Feature counts sum to the XML feature total; '
        'distinct-address counts across tickers must not be summed.', '',
        '## Current counts by program', '',
        table(['Program tag','Distinct addresses','Entity UID records'],[(p,n,len({r['sdn_uid'] for r in active if p in r['programs'].split(';')})) for p,n in sorted(report['by_program'].items())]), '',
        'Program counts overlap because an entry can carry several program tags. They are not additive.', '',
        '## Ticker → chain → trackability', '',
        'EVM hex is lowercased; Bitcoin/Litecoin bech32 is lowercased; base58 preserves case. '
        'Tron base58check and `41`-hex are converted to the same base58 canonical address; `tron_hex` preserves its equivalent hex form. '
        'No unlabelled controller identity is inferred. Native tickers identify their explicit chain. '
        'USDT/USDC use address format: `T…`/`41…` → TRX, `1…`/`3…`/`bc1…` → BTC (Omni), and `0x…` → ETH by convention. '
        '**A 20-byte EVM address cannot establish the EVM network by itself**: stablecoin EVM assignments have medium chain confidence. '
        'BNB `bnb1…` means Beacon Chain; a BNB `0x…` would mean BSC.', '',
        'One explicit source-label conflict is preserved: WANG, Mingming (UID 45404) has '
        '`TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq` labelled **XBT** in both XML formats and the '
        '[2023-10-03 action](https://ofac.treasury.gov/recent-actions/20231003). It passes Tron base58check with '
        'version `41`, so its chain is **TRX**, while `ticker=XBT` remains unchanged. '
        '`source_ticker_mismatch=true`, the mapping rule, and medium confidence expose this source anomaly. '
        'It is a valid address with a conflicting ticker label, not a silently repaired address.', '',
    ]
    mappings = defaultdict(lambda:dict(rows=set(),flags=set(),urls=set(),reasons=set()))
    for i,r in enumerate(ledger):
        for f in json.loads(r['feature_records']):
            key=(f['ticker'],f['chain'])
            d=assign(f['ticker'],f['address'])
            mappings[key]['rows'].add(i)
            mappings[key]['flags'].add(d['trackable'])
            mappings[key]['urls'].add(d['explorer_url'])
            if d['untrackable_reason']:
                mappings[key]['reasons'].add(d['untrackable_reason'])
    lines += [table(['Ticker','Chain','Trackable','Public history route / reason'],[
        (t,c,' / '.join(sorted(m['flags'])), '; '.join(sorted(m['urls']-{''} | m['reasons'])))
        for (t,c),m in sorted(mappings.items())]), '',
        '`trackable` means a public address-history route is identified; it does **not** assert any chain history has been collected or exhaustively validated by the ledger build. '
        'False rows remain in both CSVs. Monero is private; transparent Zcash is eligible and shielded/unified addresses would be excluded from public address history. '
        'Malformed addresses are false even on an otherwise trackable chain. '
        'BNB Beacon Chain’s historical explorer serves the listed address; its retirement must be considered by downstream timeline work.', '',
        'Explorer checks are reproducible with `scripts/ledger/probe_explorers.py`. Saved provider pages are indexed by `explorer_*` in the raw manifest. '
        'CryptoID’s DOGE/BTG/XVG URLs returned a generic directory, so HTTP 200 was not treated as proof of coverage. '
        'Working alternatives were identified for DOGE, LTC, ZEC, and XVG. Bitcoin Gold’s old explorer hostname and Trezor hostname did not resolve, '
        'and the Guarda endpoint returned 404; BTG remains false until a usable provider is verified. '
        'TRX, BCH, BSC, and SOL have known public explorers but this environment encountered 401/403/429 or a browser challenge; '
        'API access, pagination, and the earliest available block still need downstream verification. No chain-flow result is claimed here.', '',
        '## Malformed source values', '',
        table(['UID','Entity','Ticker','Address (literal)','Current?','Validation'],[(r['sdn_uid'],r['sdn_name'],r['ticker'],r['address'],r['current_in_sdn'],r['address_validation']) for r in malformed]), '',
        'Shape/checksum validation is explicit per row. EIP-55 and Monero Keccak checksums are not claimed. '
        'The short LIFSHITS ETH value and the older ISIL KHORASAN XMR spelling are retained with their later removal/correction dates; no source typo is silently repaired.', '',
        '## Removed addresses and replacement records', '',
        table(['UID','OFAC entry','Removed date','Address–entity rows','Action URL'],[
            (uid,name,date,n,next(r['delisted_action_url'] for r in historical if (r['sdn_uid'],r['sdn_name'],r['delisted_date'])==(uid,name,date)))
            for (uid,name,date),n in sorted(Counter((r['sdn_uid'],r['sdn_name'],r['delisted_date']) for r in historical).items())]), '',
        f'Tornado Cash UID **38499** had {sum(len(json.loads(r["feature_records"])) for r in tornado_old)} ticker features over **{len(tornado_old)} distinct addresses** in the August 2022 snapshot. '
        f'OFAC withdrew that record on 2022-11-08 and added UID **39796** with **{len(tornado_new)} ETH addresses**. '
        f'All {len(tornado_new)} replacement-record addresses were removed on **2025-03-21**. '
        f'The {len(tornado_old)} old rows are not {len(tornado_old)} additional unique addresses on top of the {len(tornado_new)}: {tornado_overlap} recur in the replacement, while '
        '`0x905b63Fff465B9fFBF41DeA908CEb12478ec7601` does not. '
        'Treasury’s delisting press release is also saved under `treasury_tornado_delisting` '
        '([source](https://home.treasury.gov/news/press-releases/sb0057)).', '',
        'Removal of an address feature does not imply that OFAC delisted its entity. '
        'LIFSHITS and ISIL KHORASAN include corrected strings; CHATEX and SOKOLOVSKI lose individual address features while their current entries remain. '
        'FAYZIMATOV’s deletion names the removed entity. The Beacon Chain address later appears under CRYPTO HOME DMCC, '
        'so its historical SOKOLOVSKI removal is not a present-day global delisting of that address.', '',
        '## 0xB10C reconciliation', '',
        f'Current list comparison is pinned to `{json.loads(read_entry(manifest["b10c_commits_1"]))[0]["sha"]}` on the `lists` branch. '
        f'**{report["b10c_commits"]} commits** and every dated patch are saved. Only public data files and diffs are read; upstream code is not executed. '
        'The earliest real address baseline is the commit explicitly described as a September 2022 squash; its 2021 author timestamp is not used as an address designation date.', '',
        f'OFAC-not-0xB10C: **{len(report["ofac_not_b10c"])} ticker/address pairs**. '
        f'0xB10C-not-OFAC: **{len(report["b10c_not_ofac"])} pairs**.', '',
        table(['Direction','Ticker','Address','Explanation'],[
            ('OFAC-not-0xB10C',t,a,'Ticker omitted by current upstream extraction support' if t in ('BNB','DOGE') else 'Requires review') for t,a in report['ofac_not_b10c']]+[
            ('0xB10C-not-OFAC',t,a,'Requires review') for t,a in report['b10c_not_ofac']]), '',
        f'Ticker differences for shared current addresses: **{len(report["ticker_differences"])}**. '
        + (table(['Address','OFAC tickers','0xB10C tickers'],report['ticker_differences']) if report['ticker_differences'] else '') +
        'Case-only differences are normalized for comparison; ticker labels from OFAC are never overwritten by the third-party list.', '',
        table(['History commit day (UTC)','Raw address deletions','Case-only changes','OFAC explanation'],[
            (date,len(v),sum(x['kind']=='case_only' for x in v),
             {'2022-11-09':'2022-11-08 withdrawal/redesignation; one case-only change',
              '2024-01-12':'CHATEX update on 2024-01-11',
              '2025-03-22':'90 Tornado Cash removals on 2025-03-21',
              '2026-08-25':'FAYZIMATOV deletion on 2026-08-24',
              '2026-09-10':'ISIL KHORASAN spelling correction on 2026-09-09'}.get(date,'Review needed'))
            for date,v in sorted(_group(report['history_removals'],'date').items())]), '',
        'All non-case historical removals correspond to retained ledger rows with dated OFAC removal evidence. '
        'The pre-squash LIFSHITS correction and unsupported BNB/SOKOLOVSKI removal were found by scanning OFAC pages, '
        'demonstrating why the GitHub history alone is insufficient.', '',
        '## Random source-text verification', '',
        f'Uniform sample without replacement from {sample.get("population",0)} sorted ledger rows; seed `{sample.get("seed","")}`. '
        f'**{len(valid_reviews)} rows** were directly reviewed against the saved Recent Actions entry text during this task. '
        'This is a computational source-text review, not an independent external human audit. '
        'Selections, exact excerpts, raw references, and review notes are retained in `scripts/ledger/manual_verification.json`. '
        'The build revalidates each saved quote against its raw page.', '',
        table(['#','UID / entry','Address','First publication / page','What OFAC says'],[
            (i,f'{r["sdn_uid"]} / {r["sdn_name"]}',r['address'],f'[{r["listed_date"]}]({r["url"]})',f'{r["section"]}: “…{r["quote"]}…” {r["finding"]}')
            for i,r in enumerate(valid_reviews,1)]), '',
        '## Remaining limits', '',
        'The current ledger is exhaustive against both saved official SDN XML formats. Historical coverage is exhaustive over the downloaded sitemap pages and saved list diffs, '
        'not a claim about pages OFAC no longer exposes. All currently known row dates and historical UIDs are resolved. '
        'Stablecoin EVM chain inference, provider accessibility, address-level full-history pagination, and three malformed strings remain explicit limitations. '
        'The ledger documents identity/action evidence and trackability; separate analyses cover balances, flows, freezes and prices.', '',
    ]
    return '\n'.join(lines).encode()

def _group(rows,key):
    out=defaultdict(list)
    for row in rows:
        out[row[key]].append(row)
    return out
