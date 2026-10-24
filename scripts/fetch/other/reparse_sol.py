"""Rebuild Solana asset rows from saved finalized transaction evidence, offline."""
from fetch import parse_sol
from sol_history import rebuild
from common import ROOT,load,save,set_bounds

def main():
    for path in (ROOT/'data/timelines/sol').glob('*.json.gz'):
        t=load(path);rebuild(t,parse_sol);set_bounds(t);save(path,t)
        t['coverage']['notes']=[n for n in t['coverage']['notes'] if not n.startswith('SOL and SPL amounts')]
        note='Parsed System/SPL instruction transfers are individual rows (is_transfer=true). Fees and non-payment balance adjustments are separate (is_transfer=false); adjustments can include rent/refunds, mint/burn and unparsed operations.'
        if note not in t['coverage']['notes']:t['coverage']['notes'].insert(0,note)
        save(path,t)
        print(t['address'],len(t['txs']),t['owner_resolution']['events_resolved_from_prior_evidence'],
              len(t['owner_resolution']['unresolved_balance_records']))

if __name__=='__main__':main()
