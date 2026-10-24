#!/usr/bin/env python3
"""Bounded keyless forward paths for flows.py's largest unlabelled destinations.

--fetch enables public API reads; otherwise only successful cached responses.
--check reproduces the saved trace bundle entirely offline from its own raw cache.
No Etherscan, credentials, ownership inference, swaps or bridge extrapolation.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import flows as f

BLOCKSCOUT={'ETH':'https://eth.blockscout.com','ARB':'https://arbitrum.blockscout.com',
            'OP':'https://optimism.blockscout.com','BASE':'https://base.blockscout.com',
            'POLYGON':'https://polygon.blockscout.com','ETC':'https://etc.blockscout.com'}
BLOCKBOOK={'BTC':'https://btc1.trezor.io','LTC':'https://ltc1.trezor.io',
           'BCH':'https://bch1.trezor.io','DOGE':'https://doge1.trezor.io','DASH':'https://dash1.trezor.io','ZEC':'https://zec1.trezor.io'}


class Gap(Exception): pass


def canonical_url(value):
    p=urllib.parse.urlsplit(value)
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(p.query,keep_blank_values=True))),p.fragment))


class Client:
    def __init__(self,fetch=False,budget=900,replay=None,replay_errors=None):
        self.fetch=fetch;self.budget=budget;self.requests=0;self.last={};self.failures=collections.Counter()
        self.used={};self.replay=replay;self.observations=[];self.errors={};self.replay_errors=replay_errors or {};self.cache_index={}

    def get(self,url):
        url=canonical_url(url)
        if self.replay is not None and url in self.replay_errors:
            if url in self.replay:self.used[url]=self.replay[url]
            self.errors[url]=self.replay_errors[url]
            raise Gap(self.errors[url])
        try:return self._get(url)
        except Gap as exc:
            self.errors[url]=str(exc);raise

    def _get(self,url):
        host=urllib.parse.urlsplit(url).netloc
        if host not in {urllib.parse.urlsplit(v).netloc for v in list(BLOCKSCOUT.values())+list(BLOCKBOOK.values())} | {'api.trongrid.io','eth1.trezor.io'}:
            raise Gap('host not allowlisted')
        key=hashlib.sha256(url.encode()).hexdigest()
        path=f.RAW/'http'/host/(key+'.json.gz')
        if not path.exists() and self.replay is None:
            # Cached JSON sorts keys; opaque cursor key order must not cause a
            # fresh request for an otherwise identical pagination URL.
            if host not in self.cache_index:
                entries={}
                for previous in (f.RAW/'http'/host).glob('*.json.gz'):
                    try:entries[canonical_url(f.load(previous)['request']['url'])]=previous
                    except (OSError,ValueError,KeyError):continue
                self.cache_index[host]=entries
            path=self.cache_index[host].get(url,path)
        if self.replay is not None:
            if url not in self.replay: raise Gap('request absent from pinned replay')
            path=f.ROOT/self.replay[url]
        if path.exists():
            envelope=f.load(path)
            object_ref=f.rel(path) if self.replay is not None else f.archive(envelope,'http_objects')
            self.used[url]=object_ref
            if envelope['status']==200 and not envelope.get('transport_error'):
                data=envelope['response']
                if isinstance(data,dict) and data.get('success') is False: raise Gap('cached API error: '+str(data)[:160])
                return data,object_ref
            if not self.fetch or self.replay is not None: raise Gap('cached HTTP failure '+str(envelope['status'])+' '+object_ref)
        if not self.fetch: raise Gap('cache miss: '+url)
        if self.requests>=self.budget: raise Gap('run request budget exhausted')
        if self.failures[host]>=2: raise Gap('host circuit open after 2 failed requests: '+host)
        for attempt in range(3):
            if self.requests>=self.budget: raise Gap('run request budget exhausted')
            time.sleep(max(0,1.25-(time.monotonic()-self.last.get(host,0))))
            self.last[host]=time.monotonic();self.requests+=1
            status=0;error=None
            try:
                request=urllib.request.Request(url,headers={'User-Agent':'LifeAfterSanctions-Research/1.0 (public chain data; cached)','Accept':'application/json'})
                with urllib.request.urlopen(request,timeout=22) as response:
                    status=response.status;body=response.read(35_000_000)
            except urllib.error.HTTPError as exc:
                status=exc.code;body=exc.read(100000)
            except (OSError,ValueError) as exc:
                body=b'';error=str(exc)[:250]
            try: data=json.loads(body)
            except ValueError: data={'unparsed_body':body.decode('utf8','replace')[:5000]}
            envelope={'request':{'method':'GET','url':url},'retrieved_at':dt.datetime.now(f.UTC).isoformat(),
                      'status':status,'response':data,'body_sha256':f.sha(body),'transport_error':error}
            # Preserve an earlier failed observation when a retry replaces the cache.
            if path.exists(): f.archive(f.load(path),'http_observations')
            f.atomic(path,gzip.compress(f.canonical(envelope),mtime=0));object_ref=f.archive(envelope,'http_objects');self.used[url]=object_ref
            self.observations.append({'url':url,'status':status,'raw_ref':object_ref})
            if status==429 or status>=500:
                if attempt<2: time.sleep(min(20,4*2**attempt));continue
            if status!=200 or error:
                self.failures[host]+=1;raise Gap('HTTP '+str(status)+' '+object_ref)
            self.failures[host]=0
            if isinstance(data,dict) and data.get('success') is False: raise Gap('API error: '+f.rel(path))
            return data,object_ref
        raise Gap('retry exhaustion')


def url(base,params): return base+'?'+urllib.parse.urlencode(sorted(params.items()))


def event(chain,address,hash_,block,when,asset,amount,dest,ref,event_id):
    parsed=f.timestamp(when)
    when=parsed.isoformat(timespec='seconds').replace('+00:00','Z') if parsed else when
    return {'chain':chain,'from':address,'to':f.normalize_address(chain,dest),'hash':hash_,'block':block,
            'time_utc':when,'asset':asset,'amount':str(amount),'raw_ref':ref,'event_id':str(event_id),
            'source_url':f.explorer(chain,hash_)}


class History:
    def __init__(self,client): self.client=client;self.cache={}

    def get(self,chain,address,asset,lower_block,lower_time,decimals):
        key=(chain,address,asset)
        cached=self.cache.get(key)
        if cached and cached['lower_time']<=lower_time and (not lower_block or cached['lower_block']<=lower_block):
            if cached.get('error'): raise Gap(cached['error'])
            return cached
        result={'lower_time':lower_time,'lower_block':int(lower_block or 0),'events':[],'complete':False,'refs':[],'prefix_end_time':None}
        try:
            if chain in BLOCKSCOUT:
                result.update(self.evm(chain,address,asset,lower_block,lower_time,decimals))
            elif chain=='TRX': result.update(self.tron(address,asset,lower_time,decimals))
            elif chain in BLOCKBOOK: result.update(self.utxo(chain,address,asset,lower_block,lower_time))
            else: raise Gap('no supported keyless route for '+chain)
        except Gap as exc:
            result['error']=str(exc);self.cache[key]=result;raise
        result['events'].sort(key=lambda e:(e['time_utc'],int(e.get('block') or 0),e['hash'],e['event_id']))
        self.cache[key]=result;return result

    def evm(self,chain,address,asset,lower_block,lower_time,decimals):
        try:return self.evm_compatible(chain,address,asset,lower_block,lower_time,decimals)
        except Gap as compatible_gap:
            try:return self.evm_v2(chain,address,asset,lower_block,lower_time,decimals)
            except Gap as v2_gap:raise Gap(str(compatible_gap)+'; v2 fallback: '+str(v2_gap))

    def evm_v2(self,chain,address,asset,lower_block,lower_time,decimals):
        """Native v2 is separately available on some Blockscout hosts.

        v2 is newest-first: complete reverse pagination down to the starting
        block is required before calling a candidate the earliest transfer.
        """
        token=asset.lower().startswith('0x')
        routes=['token-transfers'] if token else ['transactions','internal-transactions']
        events=[];refs=[]
        for route in routes:
            params={'type':'ERC-20','token':asset} if token else {}
            base=BLOCKSCOUT[chain]+'/api/v2/addresses/'+address+'/'+route
            covered=False
            for page in range(30):
                request=url(base,params) if params else base
                payload,ref=self.client.get(request);refs.append(ref)
                if not isinstance(payload,dict) or not isinstance(payload.get('items'),list):raise Gap('Blockscout v2 schema '+ref)
                items=payload['items'];oldest=None
                for i,r in enumerate(items):
                    block=int(r.get('block_number') or 0)
                    if block:oldest=min(oldest,block) if oldest is not None else block
                    when=r.get('timestamp')
                    if not when or f.timestamp(when)<f.timestamp(lower_time):continue
                    sender=r.get('from') or {};dest=r.get('to') or {}
                    sender=sender.get('hash','') if isinstance(sender,dict) else sender
                    dest=dest.get('hash','') if isinstance(dest,dict) else dest
                    if sender.lower()!=address.lower() or not dest:continue
                    if r.get('status') in ('error','failed') or r.get('success') is False:continue
                    if token:
                        info=r.get('token',{});total=r.get('total') or {}
                        if (info.get('address_hash') or '').lower()!=asset.lower():continue
                        amount=f.dec(total.get('value'))/(Decimal(10)**int(total.get('decimals',decimals)))
                    else:amount=f.dec(r.get('value'))/(Decimal(10)**decimals)
                    if amount<=0:continue
                    h=r.get('hash') or r.get('transaction_hash')
                    events.append(event(chain,address,h,block,when,asset,amount,dest,ref+'#/response/items/'+str(i),r.get('index',r.get('log_index',str(page)+':'+str(i)))))
                next_params=payload.get('next_page_params')
                if not next_params or (oldest is not None and lower_block and oldest<int(lower_block)):
                    covered=True;break
                params=dict(next_params)
                if token:params.update(type='ERC-20',token=asset)
            if not covered:raise Gap('Blockscout v2 reverse pagination budget prevents FIFO ordering proof')
        return {'events':events,'refs':refs,'complete':True,'prefix_end_time':None}

    def evm_compatible(self,chain,address,asset,lower_block,lower_time,decimals):
        token=asset.lower().startswith('0x')
        actions=['tokentx'] if token else ['txlist','txlistinternal']
        events=[];refs=[];complete=True;prefix=[]
        for action in actions:
            stream=[];exhausted=False
            for page in range(1,5):
                params={'module':'account','action':action,'address':address,'startblock':int(lower_block or 0),
                        'endblock':999999999,'page':page,'offset':1000,'sort':'asc'}
                if token: params['contractaddress']=asset
                payload,ref=self.client.get(url(BLOCKSCOUT[chain]+'/api',params));refs.append(ref)
                rows=payload.get('result') if isinstance(payload,dict) else None
                if not isinstance(rows,list):
                    raise Gap('Blockscout semantic/unsupported response '+ref+': '+str(payload)[:130])
                # Native txlist contains incoming rows too: filter sender explicitly.
                for i,r in enumerate(rows):
                    if str(r.get('from','')).lower()!=address.lower(): continue
                    if r.get('isError')=='1' or r.get('txreceipt_status')=='0': continue
                    amount=f.dec(r.get('value'))/(Decimal(10)**int(r.get('tokenDecimal',decimals) or decimals))
                    dest=r.get('to') or r.get('contractAddress')
                    when=dt.datetime.fromtimestamp(int(r['timeStamp']),f.UTC).isoformat().replace('+00:00','Z')
                    if amount<=0 or not dest or when<lower_time: continue
                    tx_asset=r.get('contractAddress',asset) if token else asset
                    if token and tx_asset.lower()!=asset.lower(): continue
                    stream.append(event(chain,address,r['hash'],int(r['blockNumber']),when,asset,amount,dest,
                        ref+'#/response/result/'+str(i),r.get('logIndex',r.get('traceId',str(page)+':'+str(i)))))
                if len(rows)<1000: exhausted=True;break
                # Prefix is sufficient after a positive outgoing transaction before the final block.
                if stream and int(stream[0]['block'])<int(rows[-1]['blockNumber']): break
            events.extend(stream);complete &= exhausted
            if rows: prefix.append(dt.datetime.fromtimestamp(int(rows[-1]['timeStamp']),f.UTC).isoformat().replace('+00:00','Z'))
        # Any unknown stream ordering stops candidates at/after the shortest checked prefix.
        return {'events':events,'complete':complete,'refs':refs,'prefix_end_time':min(prefix) if prefix and not complete else None}

    def tron(self,address,asset,lower_time,decimals):
        events=[];refs=[];minimum=int(f.timestamp(lower_time).timestamp()*1000)
        if asset=='TRX': routes=[('/transactions',False),('/internal-transactions',False)]
        elif asset.startswith('T'):routes=[('/transactions/trc20',True)]
        else:raise Gap('unsupported Tron asset '+asset)
        complete=True;prefix=[]
        for route,is_token in routes:
            params={'limit':200,'only_confirmed':'true','order_by':'block_timestamp,asc','min_timestamp':minimum}
            if is_token:params.update(contract_address=asset,only_from='true')
            next_url=url('https://api.trongrid.io/v1/accounts/'+address+route,params)
            exhausted=False;stream=[];rows=[]
            for page in range(10):
                payload,ref=self.client.get(next_url);refs.append(ref)
                if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):raise Gap('TronGrid schema '+ref)
                rows=payload['data']
                for i,r in enumerate(rows):
                    when=dt.datetime.fromtimestamp(int(r['block_timestamp'])/1000,f.UTC).isoformat().replace('+00:00','Z')
                    base_ref=ref+'#/response/data/'+str(i)
                    if is_token:
                        info=r.get('token_info',{})
                        if info.get('address')!=asset or int(info.get('decimals',-1))!=int(decimals):continue
                        if r.get('from')==address and r.get('type')=='Transfer':
                            amount=f.dec(r.get('value'))/(Decimal(10)**decimals)
                            if amount>0:stream.append(event('TRX',address,r['transaction_id'],r.get('blockNumber'),when,asset,amount,r['to'],base_ref,str(page)+':'+str(i)))
                    elif route=='/transactions':
                        if any(v.get('contractRet') not in (None,'SUCCESS') for v in r.get('ret',[])):continue
                        for j,c in enumerate(r.get('raw_data',{}).get('contract',[])):
                            v=c.get('parameter',{}).get('value',{})
                            sender=f.normalize_address('TRX',v.get('owner_address',''))
                            dest=f.normalize_address('TRX',v.get('to_address',v.get('contract_address','')))
                            amount=f.dec(v.get('amount') if c['type']=='TransferContract' else v.get('call_value') if c['type']=='TriggerSmartContract' else 0)/10**6
                            if sender==address and dest and amount>0:stream.append(event('TRX',address,r['txID'],r.get('blockNumber'),when,asset,amount,dest,base_ref,str(j)))
                    else:
                        data=r.get('data',{})
                        sender=f.normalize_address('TRX',r.get('from_address',''));dest=f.normalize_address('TRX',r.get('to_address',''))
                        if data.get('rejected') or sender!=address:continue
                        values=data.get('call_value',{})
                        if isinstance(values,dict):amount=f.dec(values.get('_',0))/10**6
                        else:amount=Decimal(0)
                        if amount>0:stream.append(event('TRX',address,r['tx_id'],r.get('blockNumber'),when,asset,amount,dest,base_ref,r.get('internal_tx_id',i)))
                next_url=payload.get('meta',{}).get('links',{}).get('next')
                if not next_url:exhausted=True;break
                if not next_url.startswith('https://api.trongrid.io/'):raise Gap('untrusted pagination URL')
                if stream and rows and stream[0]['time_utc']<when:break
            events+=stream;complete &= exhausted
            if rows:prefix.append(dt.datetime.fromtimestamp(int(rows[-1]['block_timestamp'])/1000,f.UTC).isoformat().replace('+00:00','Z'))
        return {'events':events,'refs':refs,'complete':complete,'prefix_end_time':min(prefix) if prefix and not complete else None}

    def utxo(self,chain,address,asset,lower_block,lower_time):
        events=[];refs=[];complete=False
        # Blockbook sorts newest first: require complete pagination before FIFO selection.
        for page in range(1,21):
            request=url(BLOCKBOOK[chain]+'/api/v2/address/'+address,{'details':'txs','pageSize':1000,'page':page,'from':int(lower_block or 0)})
            payload,ref=self.client.get(request);refs.append(ref)
            if not isinstance(payload,dict) or 'transactions' not in payload:
                if isinstance(payload,dict) and int(payload.get('txs',0))==0:return {'events':[],'refs':refs,'complete':True,'prefix_end_time':None}
                raise Gap('Blockbook schema '+ref)
            for i,r in enumerate(payload['transactions']):
                inputs=r.get('vin',[])
                if not any(address in v.get('addresses',[]) for v in inputs):continue
                # UTXO spend link is exact, but co-input owners and allocation are not.
                if not all(v.get('addresses')==[address] for v in inputs):raise Gap('mixed-input UTXO spend; no exact output attribution')
                when=dt.datetime.fromtimestamp(int(r['blockTime']),f.UTC).isoformat().replace('+00:00','Z')
                if when<lower_time:continue
                for j,o in enumerate(r.get('vout',[])):
                    addrs=o.get('addresses',[])
                    if len(addrs)!=1 or addrs[0]==address:continue
                    amount=f.dec(o.get('value'))/10**8
                    if amount>0:events.append(event(chain,address,r['txid'],r.get('blockHeight'),when,asset,amount,addrs[0],ref+'#/response/transactions/'+str(i),j))
            if page>=int(payload.get('totalPages',1)):complete=True;break
        if not complete:raise Gap('Blockbook reverse-pagination budget prevents FIFO proof')
        return {'events':events,'refs':refs,'complete':True,'prefix_end_time':None}


def follow(edge,history,index,reserved):
    chain=edge['chain'];addr=edge['destination_address'];asset=edge['asset'];when=edge['time_utc'];block=edge['block']
    path={'edge_id':edge['edge_id'],'chain':chain,'seed_address':addr,'seed_usd':edge['usd'],'seed_hash':edge['hash'],
          'hops':1,'status':'unresolved','terminal_class':'unlabelled','steps':[], 'reason':''}
    seen={edge['source_address'],addr}
    decimals=next((v[1] for k,v in f.TOKENS.get(chain,{}).items() if k==f.normalize_address(chain,asset)),18 if chain in f.EVM else 6 if chain=='TRX' else 8)
    for hop in range(2,6):
        try:data=history.get(chain,addr,asset,block,when,decimals)
        except Gap as exc:path.update(status='coverage_gap',reason=str(exc));break
        candidates=[];ambiguous=False;already_reserved=False
        for e in data['events']:
            # Never choose another output of the incoming transaction as a later spend.
            incoming_hash=path['steps'][-1]['hash'] if path['steps'] else edge['hash']
            if e['hash']==incoming_hash:continue
            if f.timestamp(e['time_utc'])<f.timestamp(when):continue
            if f.timestamp(e['time_utc'])==f.timestamp(when):
                # Without transaction ordering, same timestamp is not evidence of forward order.
                if not block or not e.get('block') or int(e['block'])<=int(block):ambiguous=True;continue
            if data.get('prefix_end_time') and e['time_utc']>=data['prefix_end_time']:continue
            reservation=(chain,addr,e['hash'],asset)
            if reservation in reserved:already_reserved=True;continue
            candidates.append(e)
        if ambiguous:
            path.update(status='ordering_unknown',reason='another outgoing transaction shares the incoming time without proven order');break
        if not candidates:
            path.update(status='fifo_output_already_reserved' if already_reserved else 'no_outgoing_observed' if data['complete'] else 'pagination_gap',reason='within cached data; not proof funds stayed at this address');break
        earliest=min(e['time_utc'] for e in candidates)
        first=[e for e in candidates if e['time_utc']==earliest]
        if len({e['hash'] for e in first})>1:
            path.update(status='ordering_unknown',reason='multiple outgoing transactions share earliest timestamp');break
        chosen=sorted(first,key=lambda e:(-f.dec(e['amount']),e['to'],e['event_id']))[0]
        reserved.add((chain,addr,chosen['hash'],asset))
        path['steps'].append(chosen);path['hops']=hop
        addr=chosen['to'];when=chosen['time_utc'];block=chosen.get('block')
        cls,name,labels,reason=f.classify(chain,addr,f.timestamp(when),index)
        if cls!='unlabelled':
            path.update(status='label_reached',terminal_class=cls,terminal_address=addr,terminal_label=name,
                        terminal_label_claims=labels,reason=reason);break
        if addr in seen:path.update(status='cycle',reason='address repeated');break
        seen.add(addr)
    else:path.update(status='max_hops',reason='5 hops including first receipt; no label found within checked path')
    return path


def run(result,snap,client):
    # Source Tornado contracts have their own analysis and cannot supply seeds.
    # Avoid repeatedly classifying hundreds of thousands of unrelated pool rows.
    wallet_snapshot=dict(snap);wallet_snapshot['rows']=[r for r in snap['rows'] if not r['tornado_contract']]
    edges,_=f.build_edges(wallet_snapshot); core=[e for e in edges if f.eligible(e)];selected=f.select_seeds(core)
    ids={eid for seed in selected['seeds'] for eid in seed['edges']}
    ordered=sorted([e for e in core if e['edge_id'] in ids],key=lambda e:(e['time_utc'],int(e.get('block') or 0),e['hash'],e['edge_id']))
    history=History(client);reserved=set();paths=[];index=f.index_addresses(snap)
    for i,e in enumerate(ordered):
        paths.append(follow(e,history,index,reserved))
        if i%20==0:print(json.dumps({'paths_done':i+1,'total_paths':len(ordered),'requests':client.requests,'outcomes':dict(collections.Counter(p['status'] for p in paths))}),flush=True)
    return {'schema_version':1,'snapshot_ref':result['snapshot_ref'],'hop_rule':f.HOP_RULE,
            'paths':paths,'requests':client.used,'request_errors':client.errors,'notes':[
              'Paths are temporal same-asset observations under the documented heuristic, not uniquely attributed funds.',
              'Successful HTTP raw responses and failed observations are gzip-cached with request URLs, retrieval times and hashes.',
              'All selected first-hop receipt edges are attempted FIFO; each downstream outgoing transaction is reserved once. Unknown history/order and supported-route gaps are explicit.',
              'No Etherscan, keys, transfers, swaps, asset substitutions, contract execution or inferred owners. Host request spacing is 1.25 seconds.',
              'CEX/mixer hop distribution is conditional on labels and prefix coverage; unresolved paths are censored, never zero hops.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fetch',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--budget',type=int,default=900);p.add_argument('--self-test',action='store_true');args=p.parse_args()
    if args.self_test:
        class FakeHistory:
            def get(self,*args):return {'events':[event('ETH','b','later',2,'2022-08-09T00:00:00Z','ETH',2,'c','raw',1),event('ETH','b','later',2,'2022-08-09T00:00:00Z','ETH',5,'d','raw',2)],'complete':True,'prefix_end_time':None}
        old=f.classify
        f.classify=lambda *args:('mixer','source label',[],'test')
        e={'chain':'ETH','destination_address':'b','source_address':'a','asset':'ETH','time_utc':'2022-08-08T00:00:00Z','block':1,'edge_id':'e','usd':'4','hash':'initial'}
        out=follow(e,FakeHistory(),{},set());assert out['hops']==2 and out['terminal_address']=='d'
        f.classify=old;print('PASS: earliest transaction / largest output / first labelled hop');return 0
    result=f.load(f.RESULT);snap=f.load(f.ROOT/result['snapshot_ref'])
    for path,expected in (snap['shared_hashes']|snap['price_hashes']).items():
        if f.sha((f.ROOT/path).read_bytes())!=expected:raise RuntimeError('Shared dependencies changed; rerun flows.py first: '+path)
    pointer=f.RAW/'trace_latest.json.gz';published=f.load(pointer) if pointer.exists() else None
    if args.check:
        if not published or published['snapshot_ref']!=result['snapshot_ref']:raise RuntimeError('No trace bundle for current snapshot')
        client=Client(replay=published['requests'],replay_errors=published.get('request_errors'));bundle=run(result,snap,client)
        expected=dict(published);expected.pop('bundle_ref',None)
        if bundle!=expected:print('DIFF: trace paths or request manifest');return 1
        print('PASS: trace paths reproduce offline from pinned raw request cache');return 0
    client=Client(fetch=args.fetch,budget=args.budget);bundle=run(result,snap,client)
    ref=f.archive(bundle,'traces');bundle['bundle_ref']=ref
    f.atomic(pointer,gzip.compress(f.canonical(bundle),mtime=0))
    print(json.dumps({'bundle_ref':ref,'paths':len(bundle['paths']),'network_requests':client.requests,'outcomes':dict(collections.Counter(p['status'] for p in bundle['paths']))},indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
