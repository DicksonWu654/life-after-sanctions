"""Archive public explorer landing pages; HTTP 200 alone is not coverage proof.

Does not fetch chain history, use keys, or bypass provider challenges.
"""
import argparse
import datetime as dt
import json
import time
from chains import EXPLORERS
from sources import fetch, RAW, atomic, index

EXTRA = {
    'BNB_address':'https://explorer.bnbchain.org/address/bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23',
    'BTG_old':'https://explorer.bitcoingold.org/insight/',
    'BTG_trezor':'https://btg1.trezor.io/',
    'BTG_guarda':'https://btgbook.guarda.co/',
    'BTG_directory':'https://chainz.cryptoid.info/btg/',
    'BCH_alternative':'https://bch.loping.net/',
}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch',action='store_true',help='Refresh existing probe responses too')
    args=parser.parse_args()
    probes=[]
    for chain,url in {**EXPLORERS,**EXTRA}.items():
        key='explorer_probe_'+chain
        stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        try:
            fetch(key,url,refresh=args.fetch,timeout=15,attempts=2)
            meta=index()[key]
            probes.append(dict(chain=chain,url=url,observed_at=stamp,status=meta['status'],
                               final_url=meta['final_url'],raw_ref=meta['raw_ref']))
        except Exception as exc:
            probes.append(dict(chain=chain,url=url,observed_at=stamp,status=getattr(exc,'code',None),error=str(exc)))
        print(chain,probes[-1].get('status'),probes[-1].get('error',''),flush=True)
        time.sleep(.3)
    atomic(RAW/'explorer_probes.json',(json.dumps(probes,indent=2)+'\n').encode())

if __name__=='__main__':
    main()
