"""Check indexer zero-fee originator rows against read-only node receipts."""
import argparse
import json
from common import Client,ROOT,acquire_address_lock,amount,load,now,save,timeline_path
from fetch import API,decode58


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--address',required=True)
    args=parser.parse_args()
    decode58(args.address)
    client=Client()
    with acquire_address_lock('trx',args.address):
        path=timeline_path('trx',args.address)
        timeline=load(path)
        resolutions=timeline.setdefault('fee_resolution',{})
        rows=[]
        for event in timeline['txs']:
            if event.get('event_type')!='transaction_fee':continue
            if event['fee']!='0' and event['hash'] not in resolutions:continue
            receipt,ref=client.request(API+'/wallet/gettransactioninfobyid',{'value':event['hash']},group='receipts')
            if receipt.get('id')!=event['hash']:
                raise ValueError('Invalid receipt '+ref)
            fee=int(receipt.get('fee',0))
            proof=ref+('#/response/fee' if 'fee' in receipt else '#/response')
            resolutions[event['hash']]={'fee_sun':fee,'raw_ref':proof}
            event.update(fee=amount(fee),fee_raw_ref=proof,indexed_fee_sun='0')
            rows.append({'hash':event['hash'],'indexed_fee_sun':'0','receipt_fee_sun':str(fee),
                         'transaction_raw_ref':event['raw_ref'],'receipt_raw_ref':proof})
        save(path,timeline)
        report={'checked_at':now(),'address':args.address,'zero_indexed_fee_checks':rows,
                'corrected_fee_sun':str(sum(int(r['receipt_fee_sun']) for r in rows)),
                'network_calls':client.calls,'cache_hits':client.hits}
        save(ROOT/'data/raw/tron/fee-audits'/(args.address+'.json.gz'),report)
        print(json.dumps(report),flush=True)


if __name__=='__main__':main()
