"""Tron refresh performance regressions without weakening the shared quota."""
import sys,unittest,time,tempfile
from pathlib import Path
from unittest.mock import patch,MagicMock
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'fetch/tron'))
import fetch,common
class IncrementalPerformance(unittest.TestCase):
 def test_shared_head_updates_caller_and_reuses_nearby_snapshot(self):
  client=MagicMock();client.request.return_value=({'block_header':{'raw_data':{'timestamp':2000,'number':2}}},'new-head')
  client.get.return_value=({'success':True,'data':[],'meta':{}},'tail')
  head={'timestamp':1000,'number':1,'raw_ref':'old','_observed':0}
  args=SimpleNamespace(refresh=True,history_only=True,max_pages=10,no_labels=False)
  with tempfile.TemporaryDirectory() as directory,patch('common.ROOT',Path(directory)):
   fetch.fetch_one(client,{'address':'fixture-a'},args,head)
   fetch.fetch_one(client,{'address':'fixture-b'},args,head)
  self.assertEqual(head['timestamp'],2000)
  client.request.assert_called_once()
 def test_shared_rate_gate_remains_and_duplicate_completion_delay_is_removed(self):
  client=common.Client();client.last['api.trongrid.io']=time.monotonic()
  response=MagicMock();response.status=200;response.read.return_value=b'{}'
  response.__enter__.return_value=response
  with tempfile.TemporaryDirectory() as directory,patch('common.ROOT',Path(directory)),patch.object(client,'rate_gate') as gate,patch('common.time.sleep') as sleep,patch('common.urllib.request.urlopen',return_value=response):
   client.request('https://api.trongrid.io/test')
   gate.assert_called_once_with('api.trongrid.io');sleep.assert_not_called()
if __name__=='__main__':unittest.main()
