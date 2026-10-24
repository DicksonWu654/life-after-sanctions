"""Offline regressions for actual OFAC date, removal, and chain edge cases."""
import json
import unittest
from unittest.mock import patch
from build_ledger import derive
from chains import assign
from report import render

class EvidenceRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Offline tests must not use network')):
            cls.rows,cls.addresses,cls.actions,cls.counts,cls.pages,cls.manifest=derive()

    def row(self,uid,address):
        return next(r for r in self.rows if r['sdn_uid']==uid and r['address_normalized']==address.lower())

    def test_all_official_features_survive_grouping(self):
        current=[r for r in self.rows if r['current_in_sdn']=='true']
        self.assertEqual(sum(r['feature_count'] for r in current),self.counts['feature_count'])
        self.assertEqual(len({r['address_normalized'] for r in current}),self.counts['distinct_source_addresses'])
        self.assertEqual(len({(r['address_normalized'],r['sdn_uid']) for r in self.rows}),len(self.rows))

    def test_later_address_addition_not_entity_designation(self):
        r=self.row('27307','0x098b716b8aaf21512996dc57eb0615e2383e2f96')
        self.assertEqual(r['listed_date'],'2022-04-14')
        self.assertTrue(r['listed_action_url'].endswith('/20220414'))

    def test_tornado_replacement_and_first_publication(self):
        address='0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc'
        old=self.row('38499',address)
        new=self.row('39796',address)
        self.assertEqual(old['listed_date'],'2022-08-08')
        self.assertEqual(old['delisted_date'],'2022-11-08')
        self.assertEqual(new['listed_date'],'2022-08-08')
        self.assertEqual(new['entity_record_listed_date'],'2022-11-08')
        self.assertEqual(new['delisted_date'],'2025-03-21')

    def test_removed_malformed_value_not_silently_repaired(self):
        old=self.row('29702','0xa7e5d5a720f06526557c513402f2e6b5fa20b00')
        new=self.row('29702','0xa7e5d5a720f06526557c513402f2e6b5fa20b008')
        self.assertEqual(old['address_valid'],'false')
        self.assertEqual(old['delisted_date'],'2021-11-08')
        self.assertEqual(new['listed_date'],'2021-11-08')
        self.assertEqual(new['address_valid'],'true')

    def test_shared_evm_address_keeps_every_chain(self):
        address='0x4f47bc496083c727c5fbe3ce9cdf2b0f6496270c'
        row=self.row('42498',address)
        self.assertEqual(set(row['chains'].split(';')),{'ETH','ARB','BSC'})
        self.assertEqual({r['chain'] for r in self.addresses if r['address_normalized']==address},{'ETH','ARB','BSC'})

    def test_tron_representations_round_trip(self):
        first=assign('USDT','TNiq9AXBp9EjUqhDhrwrfvAA8U3GUQZH81')
        second=assign('USDT',first['tron_hex'])
        self.assertEqual(first['address_normalized'],second['address_normalized'])
        self.assertTrue(first['tron_hex'].startswith('41'))

    def test_beacon_chain_is_not_bsc(self):
        r=assign('BNB','bnb136ns6lfw4zs5hg4n85vdthaad7hq5m4gtkgf23')
        self.assertEqual(r['chain'],'BNB')
        self.assertEqual(r['address_valid'],'true')
        self.assertEqual(r['trackable'],'true')

    def test_mislabeled_xbt_tron_address_keeps_source_ticker(self):
        row=next(r for r in self.rows if r['sdn_uid']=='45404' and r['address']=='TUCsTq7TofTCJRRoHk6RvhMoS2mJLm5Yzq')
        self.assertEqual(row['ticker'],'XBT')
        self.assertEqual(row['chain'],'TRX')
        self.assertEqual(row['address_valid'],'true')
        self.assertEqual(row['source_ticker_mismatch'],'true')

    def test_random_verification_quotes_still_match(self):
        text=render(self.rows,self.addresses,self.actions,self.counts,self.pages,self.manifest).decode()
        self.assertIn('| Source-text-reviewed random rows | 20 / 20 |',text)

if __name__=='__main__':
    unittest.main()
