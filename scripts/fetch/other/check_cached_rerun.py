"""Prove a completed XRP/Solana/Beacon rerun makes no history requests."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tron'))
from common import ROOT,load,now,save


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--addresses',default='data/addresses.csv')
    args=parser.parse_args()
    directory=ROOT/'data/raw/other'
    groups=('sol/signatures','sol/transactions','xrp/account_tx','bnb/explorer-history')
    before={p for group in groups for p in (directory/group).glob('*.json.gz')}
    started=now()
    command=[sys.executable,str(ROOT/'scripts/fetch/other/fetch.py'),'--addresses',args.addresses]
    log=directory/'completed-rerun-final-check.log'
    with log.open('w') as output:
        result=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    after={p for group in groups for p in (directory/group).glob('*.json.gz')}
    new=sorted(str(p.relative_to(ROOT)) for p in after-before)
    statuses=[json.loads(line) for line in log.read_text().splitlines() if line.startswith('{')]
    report={'started_at':started,'checked_at':now(),'command':command,'exit_code':result.returncode,
            'completed_rerun_history_requests':len(new),'new_history_raw_refs':new,
            'log_ref':str(log.relative_to(ROOT)),'statuses':statuses,
            'run_summary':load(directory/'run-summary.json.gz'),
            'prior_refresh_logs':[f'data/raw/other/{chain}/refresh-check-{i}.log' for chain in ('sol','xrp') for i in (1,2)]}
    save(directory/'incremental-validation.json.gz',report)
    print(json.dumps({'exit_code':result.returncode,'history_requests':len(new),'address_records':len(statuses)}))
    return 1 if result.returncode or new else 0


if __name__=='__main__':raise SystemExit(main())
