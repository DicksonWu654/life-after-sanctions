"""Exact net-balance/fee separation across account-based chains."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
from fetch import parse_xrp,parse_sol
from sol_history import rebuild
from common import save

class OtherTests(unittest.TestCase):
    def test_xrp_fee_only_operation(self):
        entry={'tx':{'Account':'owner','Fee':'45','hash':'h','ledger_index':7,'date':1,'TransactionType':'AccountSet'},
               'meta':{'AffectedNodes':[{'ModifiedNode':{'LedgerEntryType':'AccountRoot',
                   'FinalFields':{'Account':'owner','Balance':'9999955'},'PreviousFields':{'Balance':'10000000'}}}]}}
        r=parse_xrp(entry,'owner','fixture')[0]
        self.assertEqual(r['amount'],'0.000000')
        self.assertEqual(r['fee'],'0.000045')
        self.assertEqual(r['direction'],'self')

    def test_sol_failed_transaction_preserves_fee(self):
        tx={'slot':9,'blockTime':1700000000,
            'transaction':{'signatures':['h'],'message':{'accountKeys':[{'pubkey':'owner'},{'pubkey':'program'}]}},
            'meta':{'preBalances':[10000000,0],'postBalances':[9995000,0],
                    'fee':5000,'err':{'InstructionError':[0,'Custom']}}}
        r,owned=parse_sol(tx,'owner','fixture')
        self.assertEqual(len(r),1)
        self.assertEqual(Decimal(r[0]['amount']),0)
        self.assertEqual(Decimal(r[0]['fee']),Decimal('.000005'))
        self.assertEqual(r[0]['status'],'FAILED')

    def test_old_spl_owner_omission_is_resolved_from_initialization(self):
        # Incoming token balance metadata lacks owner. A same-transaction
        # initializeAccount instruction proves ownership; current ownership
        # alone is deliberately absent from this fixture.
        tx={'slot':9,'blockTime':1700000000,'transaction':{'signatures':['h'],
            'message':{'accountKeys':['payer','token-account'],'instructions':[{
                'program':'spl-token','parsed':{'type':'initializeAccount',
                    'info':{'account':'token-account','owner':'owner'}}}]}},
            'meta':{'preBalances':[10000,0],'postBalances':[5000,0],'fee':5000,'err':None,
                'preTokenBalances':[],'postTokenBalances':[{'accountIndex':1,'mint':'mint',
                    'uiTokenAmount':{'amount':'1234567890123456','decimals':6}}]}}
        t={'address':'owner','txs':[],'fetch_state':{'processed':['h'],'signatures':{'h':{}},
              'signature_streams':{'owner':{'complete':True}}}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            save(root/'data/raw/other/sol/transactions/fixture.json.gz',{
                'request':{'json':{'method':'getTransaction','params':['h',{}]}},'response':{'result':tx}})
            with patch('sol_history.ROOT',root):rebuild(t,parse_sol)
        self.assertEqual(t['txs'][0]['amount'],'1234567890.123456')
        self.assertTrue(t['txs'][0]['owner_resolution_raw_refs'])
        self.assertEqual(t['owner_resolution']['unresolved_balance_records'],[])

if __name__=='__main__':unittest.main()
