"""Replay a published generation across its real 31-day flag boundary."""
import csv
import datetime as dt
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import export_site
from scripts.lib import published_inputs
from scripts.lib.pipeline_io import ROOT, write_json
from scripts.lib.site_export_io import compare_exports
from scripts.lib.price_check_clock import pin


ADDRESS = 'TAkpWPt2JZdiLSkG7ZX2VAQkZQsnGZ1nqh'
GENERATION = '2026-10-23T21:28:39Z'
BEFORE = dt.datetime(2026, 10, 23, 21, 37, 53, tzinfo=dt.timezone.utc)
AFTER = dt.datetime(2026, 10, 23, 23, 17, 50, tzinfo=dt.timezone.utc)
REAL_DATETIME = dt.datetime


def fixture(root):
    source = {'chain':'TRX', 'address':ADDRESS, 'address_normalized':ADDRESS,
              'trackable':'true', 'first_listed_date':'2020-01-01',
              'listed_date':'2020-01-01', 'listed_action_url':'https://example.org/action',
              'listed_raw_ref':'raw', 'sdn_uid':'1', 'sdn_name':'SAVED OFAC NAME',
              'ticker':'TRX', 'programs':'TEST', 'raw_ref':'raw',
              'source_url':'https://example.org/action', 'delisted_date':''}
    for name in ('ledger', 'addresses'):
        path = root/f'data/{name}.csv'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(source))
            writer.writeheader(); writer.writerow(source)
    write_json(root/f'data/timelines/trx/{ADDRESS}.json', {
        'coverage':{'complete':True}, 'balance_now':[],
        'txs':[{'time_utc':'2026-09-22T22:51:57Z', 'direction':'in',
                'asset':'TRX', 'symbol':'TRX', 'amount':'0.000001', 'hash':'saved-payment'}]})
    info = {'path':'snapshot', 'created_at_utc':GENERATION, 'timeline_sha256':{'trx/address.json':'hash'}}
    write_json(root/'snapshot/manifest.json', info)
    return info


def site_bytes(root):
    return {str(p.relative_to(root/'site/data')):p.read_bytes()
            for p in (root/'site/data').rglob('*.json')}


def frozen_clock(at):
    class Frozen(REAL_DATETIME):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    return patch.object(export_site.dt, 'datetime', Frozen)


class DeterministicExportChecks(unittest.TestCase):
    def test_native_price_coverage_replays_saved_day_and_detects_real_gaps(self):
        native = runpy.run_path(str(ROOT/'scripts/prices/price.py'), run_name='price_clock_regression')
        function = native['daily_gaps']
        namespace = function.__globals__
        saved_rows = [{'valuation_time_utc':day} for day in ('2026-10-21','2026-10-22')]
        namespace['parse_daily_csv'] = lambda symbol:saved_rows
        asset = {'symbol':'TEST', 'start_date':'2026-10-21'}
        # Native runtime behavior after midnight incorrectly demands a new day.
        namespace['DAILY_TARGET'] = dt.date(2026,10,23)
        self.assertEqual(function(asset,{}), ['2026-10-23'])
        pin(namespace,GENERATION)
        self.assertEqual(function(asset,{}), [])
        saved_rows.pop()
        self.assertEqual(function(asset,{}), ['2026-10-22'])
        with self.assertRaises(ValueError): pin(namespace,'2026-10-23T21:28:39')

    def test_actual_age_boundary_replays_every_byte_from_generation_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); info = fixture(root)
            with patch.object(published_inputs, 'ROOT', root):
                with frozen_clock(BEFORE):
                    export_site._export(root, input_snapshot=info)
                first = site_bytes(root)
                row = json.loads(first['addresses.json'])[0]
                detail = json.loads(first[f'address/trx/{ADDRESS}.json'])
                self.assertIn('still_receiving', row['flags'])
                self.assertEqual(row['flags'], detail['flags'])
                self.assertEqual(json.loads(first['meta.json'])['exported_at_utc'], GENERATION)
                with frozen_clock(AFTER):
                    export_site._export(root, check=True, input_snapshot=info)
                    export_site._export(root, input_snapshot=info)
                self.assertEqual(site_bytes(root), first)
                # A genuinely newer input generation must age the flag out.
                with frozen_clock(AFTER):
                    export_site._export(root, input_snapshot=dict(info, created_at_utc='2026-10-23T23:17:50Z'))
                self.assertNotIn('still_receiving', json.loads(site_bytes(root)['addresses.json'])[0]['flags'])

    def test_legacy_recorded_clock_fallback_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            write_json(root/'site/data/meta.json', {'exported_at_utc':GENERATION})
            with frozen_clock(BEFORE): export_site._export(root)
            first = site_bytes(root)
            with frozen_clock(AFTER):
                export_site._export(root, check=True)
                export_site._export(root)
            self.assertEqual(site_bytes(root), first)

    def test_no_recorded_clock_stays_explicitly_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            with frozen_clock(BEFORE): export_site._export(root)
            first = site_bytes(root)
            meta = json.loads(first['meta.json'])
            self.assertIsNone(meta['generation_at_utc'])
            self.assertEqual(meta['missing']['export.generation_at_utc'], 1)
            with frozen_clock(AFTER): export_site._export(root, check=True)
            self.assertEqual(site_bytes(root), first)

    def test_hash_seed_and_map_insertion_order_cannot_change_site_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            code = '''
import sys
from pathlib import Path
from scripts import export_site
from scripts.lib import published_inputs
from scripts.lib.pipeline_io import read_json
root=Path(sys.argv[1]);published_inputs.ROOT=root
statuses={k:{'stale':False} for k in {'tron','prices','ledger','freezes'}}
export_site._export(root,source_status=statuses,input_snapshot=read_json(root/'snapshot/manifest.json'))
'''
            for seed in ('1', '2'):
                result = subprocess.run([sys.executable, '-S', '-B', '-c', code, str(root)],
                                        cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                if seed == '1': first = site_bytes(root)
                else: self.assertEqual(site_bytes(root), first)

    def test_check_rejects_timestamp_format_and_file_set_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); a = root/'a'; b = root/'b'
            for folder in (a, b):
                write_json(folder/'meta.json', {'exported_at_utc':GENERATION})
            compare_exports(a, b)
            write_json(b/'meta.json', {'exported_at_utc':'2026-10-24T00:00:00Z'})
            with self.assertRaisesRegex(RuntimeError, r'\$\.exported_at_utc'): compare_exports(a, b)
            (b/'meta.json').write_bytes((a/'meta.json').read_bytes()+b' ')
            with self.assertRaisesRegex(RuntimeError, 'serialization bytes'): compare_exports(a, b)
            (b/'meta.json').write_bytes((a/'meta.json').read_bytes())
            write_json(b/'extra.json', {})
            with self.assertRaisesRegex(RuntimeError, 'file set differs'): compare_exports(a, b)


if __name__ == '__main__': unittest.main()
