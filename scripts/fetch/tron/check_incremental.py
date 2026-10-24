"""Exercise two real refreshes and a completed rerun, preserving request proof."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from common import ROOT,load,now,save,timeline_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addresses',default='data/addresses.csv')
    parser.add_argument('--address',default='TA3941uFAvmVibSkQ6fMJXxmaSNovX86mz')
    args=parser.parse_args()
    path=timeline_path('trx',args.address)
    initial=load(path)
    if not initial['coverage']['complete']:
        raise SystemExit('Choose a completed address with no active writer')
    directory=ROOT/'data/raw/tron'
    runs=[]
    history_refs={}
    for i,refresh in enumerate((True,True,False),1):
        before={group:set((directory/group).glob('*.json.gz')) for group in ('native','trc20','internal')}
        log=directory/('solid-refresh-check-'+str(i)+'.log')
        command=[sys.executable,str(ROOT/'scripts/fetch/tron/fetch.py'),'--addresses',args.addresses,'--address',args.address]
        if refresh:command.append('--refresh')
        with log.open('w') as output:
            result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        if result.returncode:raise SystemExit('Fetch failed; see '+str(log))
        statuses=[]
        for line in log.read_text().splitlines():
            try:statuses.append(json.loads(line))
            except ValueError:pass
        status=next((r for r in reversed(statuses) if 'streams_complete' in r),None)
        if not status or not all(status['streams_complete'].values()):
            raise SystemExit('Refresh did not finish; see '+str(log))
        new={group:sorted(str(p.relative_to(ROOT)) for p in set((directory/group).glob('*.json.gz'))-before[group]) for group in before}
        # Other address partitions may run concurrently. Only count this wallet.
        selected={group:[ref for ref in refs if '/v1/accounts/'+args.address+'/' in load(ROOT/ref)['request']['url']] for group,refs in new.items()}
        history_refs[str(i)]=selected
        status.update(mode='refresh' if refresh else 'completed default rerun',log_ref=str(log.relative_to(ROOT)),
                      history_requests=sum(map(len,selected.values())))
        runs.append(status)
        print(json.dumps(status),flush=True)
    if runs[-1]['history_requests']:
        raise SystemExit('Completed default rerun unexpectedly queried history')
    final=load(path)
    save(directory/'incremental-validation.json.gz',{'checked_at':now(),'address':args.address,
        'runs':runs,'completed_rerun_history_requests':runs[-1]['history_requests'],
        'history_raw_refs':history_refs,'balance_raw_refs':[b['raw_ref'] for b in final['balance_now']],
        'history_head_finality':final['coverage'].get('history_head_finality'),
        'timeline_ref':str(path.relative_to(ROOT))})


if __name__=='__main__':main()
